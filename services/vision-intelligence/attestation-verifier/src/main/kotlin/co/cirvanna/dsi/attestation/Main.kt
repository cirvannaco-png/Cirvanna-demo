package co.cirvanna.dsi.attestation

import com.android.keyattestation.verifier.AttestationApplicationId
import com.android.keyattestation.verifier.AttestationApplicationIdConstraint
import com.android.keyattestation.verifier.AttestationPackageInfo
import com.android.keyattestation.verifier.ChallengeChecker
import com.android.keyattestation.verifier.ConstraintConfig
import com.android.keyattestation.verifier.GoogleTrustAnchors
import com.android.keyattestation.verifier.InstantSource
import com.android.keyattestation.verifier.SecurityLevel
import com.android.keyattestation.verifier.SecurityLevelConstraint
import com.android.keyattestation.verifier.VerificationResult
import com.android.keyattestation.verifier.Verifier
import com.android.keyattestation.verifier.VerifiedBootState
import com.android.keyattestation.verifier.challengecheckers.ChallengeMatcher
import com.google.gson.Gson
import com.google.gson.JsonObject
import com.google.protobuf.ByteString
import java.io.ByteArrayInputStream
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.security.Signature
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate
import java.time.Instant
import java.math.BigInteger
import java.util.Base64

private const val MAX_CHAIN_CERTIFICATES = 8
private const val MAX_CERTIFICATE_BYTES = 24 * 1024
private const val MAX_MANIFEST_BYTES = 128 * 1024

private data class VerificationOutput(
    val verified: Boolean,
    val code: String,
    val security_level: String? = null,
    val verified_boot_state: String? = null,
    val device_locked: Boolean? = null,
    val manifest_sha256: String? = null,
)

private fun decodeBase64Url(value: String, field: String): ByteArray {
    require(value.isNotBlank()) { "missing $field" }
    require(value.matches(Regex("^[A-Za-z0-9_-]+$"))) { "invalid $field encoding" }
    return Base64.getUrlDecoder().decode(value)
}

private fun sha256Hex(bytes: ByteArray): String =
    MessageDigest.getInstance("SHA-256")
        .digest(bytes)
        .joinToString("") { "%02x".format(it.toInt() and 0xff) }

private fun hexBytes(value: String): ByteArray {
    require(value.matches(Regex("^[a-f0-9]{64}$"))) { "invalid signing certificate digest" }
    return ByteArray(32) { index ->
        value.substring(index * 2, index * 2 + 2).toInt(16).toByte()
    }
}

private fun verify(input: JsonObject): VerificationOutput {
    val challenge = decodeBase64Url(input.get("challenge_b64url").asString, "challenge")
    require(challenge.size == 32) { "invalid challenge length" }

    val packageName = input.get("package_name").asString
    require(packageName.matches(Regex("^[A-Za-z0-9_]+(\\.[A-Za-z0-9_]+)+$"))) {
        "invalid package name"
    }
    val minimumVersionCode = input.get("minimum_package_version_code").asString.toBigInteger()
    require(minimumVersionCode > BigInteger.ZERO) { "invalid minimum package version" }

    val signingCertificateDigest = hexBytes(input.get("signing_certificate_sha256").asString)
    val manifestBytes = decodeBase64Url(input.get("manifest_base64url").asString, "manifest")
    require(manifestBytes.isNotEmpty() && manifestBytes.size <= MAX_MANIFEST_BYTES) {
        "invalid manifest size"
    }
    val manifestDigest = sha256Hex(manifestBytes)
    require(manifestDigest == input.get("manifest_sha256").asString) {
        "manifest digest mismatch"
    }
    val signatureBytes = decodeBase64Url(input.get("manifest_signature_base64url").asString, "signature")
    require(signatureBytes.isNotEmpty() && signatureBytes.size <= 256) { "invalid signature size" }

    val encodedChain = input.getAsJsonArray("attestation_certificate_chain_base64url")
    require(encodedChain.size() in 2..MAX_CHAIN_CERTIFICATES) { "invalid attestation chain length" }
    val certificateFactory = CertificateFactory.getInstance("X.509")
    val chain = encodedChain.map { element ->
        val encoded = decodeBase64Url(element.asString, "certificate")
        require(encoded.isNotEmpty() && encoded.size <= MAX_CERTIFICATE_BYTES) {
            "invalid certificate size"
        }
        certificateFactory.generateCertificate(ByteArrayInputStream(encoded)) as X509Certificate
    }
    require(chain.first().publicKey.algorithm.equals("EC", ignoreCase = true)) {
        "attested signing key must be EC"
    }

    val revokedSerials = input.getAsJsonArray("revoked_serials")
        .map { it.asString.lowercase() }
        .toSet()
    require(revokedSerials.size <= 100_000) { "revocation list too large" }

    val expectedApplicationId = AttestationApplicationId(
        packages = setOf(AttestationPackageInfo(packageName, minimumVersionCode)),
        signatures = setOf(ByteString.copyFrom(signingCertificateDigest)),
    )
    val constraints = ConstraintConfig(
        attestationApplicationId = AttestationApplicationIdConstraint.STRICT,
        securityLevel = SecurityLevelConstraint.NOT_SOFTWARE,
    )
    val verifier = Verifier(
        GoogleTrustAnchors,
        { revokedSerials },
        InstantSource { Instant.now() },
        expectedApplicationId,
        constraints,
    )

    val result = verifier.verify(chain, ChallengeMatcher(challenge))
    if (result !is VerificationResult.Success) {
        return VerificationOutput(false, "ANDROID_KEY_ATTESTATION_REJECTED")
    }

    if (result.securityLevel != SecurityLevel.TRUSTED_ENVIRONMENT &&
        result.securityLevel != SecurityLevel.STRONG_BOX
    ) {
        return VerificationOutput(false, "HARDWARE_SECURITY_LEVEL_REJECTED")
    }
    if (result.verifiedBootState != VerifiedBootState.VERIFIED || !result.deviceLocked) {
        return VerificationOutput(false, "VERIFIED_BOOT_OR_LOCK_STATE_REJECTED")
    }

    val signatureVerifier = Signature.getInstance("SHA256withECDSA")
    signatureVerifier.initVerify(result.publicKey)
    signatureVerifier.update(manifestBytes)
    if (!signatureVerifier.verify(signatureBytes)) {
        return VerificationOutput(false, "CAPTURE_MANIFEST_SIGNATURE_REJECTED")
    }

    return VerificationOutput(
        verified = true,
        code = "ANDROID_KEY_ATTESTATION_VERIFIED",
        security_level = when (result.securityLevel) {
            SecurityLevel.STRONG_BOX -> "strongbox"
            SecurityLevel.TRUSTED_ENVIRONMENT -> "trusted_environment"
            else -> "software"
        },
        verified_boot_state = "verified",
        device_locked = true,
        manifest_sha256 = manifestDigest,
    )
}

fun main() {
    val gson = Gson()
    try {
        val inputText = generateSequence(::readLine).joinToString("\n")
        require(inputText.isNotBlank() && inputText.length <= 2_000_000) { "invalid request" }
        val input = gson.fromJson(inputText, JsonObject::class.java)
            ?: error("invalid request")
        val result = verify(input)
        println(gson.toJson(result))
        if (!result.verified) kotlin.system.exitProcess(2)
    } catch (_: Throwable) {
        // Do not emit certificate details, device identifiers, nonce bytes or verifier internals.
        println(gson.toJson(VerificationOutput(false, "ANDROID_ATTESTATION_VERIFICATION_FAILED")))
        kotlin.system.exitProcess(2)
    }
}
