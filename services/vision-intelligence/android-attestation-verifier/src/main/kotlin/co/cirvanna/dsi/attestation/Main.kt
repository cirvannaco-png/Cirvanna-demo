package co.cirvanna.dsi.attestation

import com.android.keyattestation.verifier.AttestationApplicationId
import com.android.keyattestation.verifier.AttestationApplicationIdConstraint
import com.android.keyattestation.verifier.AttestationPackageInfo
import com.android.keyattestation.verifier.ConstraintConfig
import com.android.keyattestation.verifier.GoogleTrustAnchors
import com.android.keyattestation.verifier.SecurityLevel
import com.android.keyattestation.verifier.VerificationResult
import com.android.keyattestation.verifier.VerifiedBootState
import com.android.keyattestation.verifier.Verifier
import com.android.keyattestation.verifier.challengecheckers.ChallengeMatcher
import com.google.gson.Gson
import com.google.gson.JsonArray
import com.google.gson.JsonElement
import com.google.gson.JsonObject
import com.google.gson.JsonParser
import com.google.protobuf.ByteString
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.math.BigDecimal
import java.math.BigInteger
import java.net.HttpURLConnection
import java.net.URI
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.security.Signature
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate
import java.time.Instant
import java.util.Base64

private const val UPSTREAM_COMMIT = "f1e8e0f46d0c8272a47ae0f30f82a3a378fdecca"
private const val MAX_REQUEST_BYTES = 512 * 1024
private const val MAX_MANIFEST_BYTES = 128 * 1024
private const val MAX_CHAIN_CERTIFICATES = 8
private const val MAX_CERTIFICATE_BYTES = 64 * 1024
private const val MAX_CHAIN_BYTES = 256 * 1024
private const val MAX_STATUS_BYTES = 2 * 1024 * 1024
private const val STATUS_URL = "https://android.googleapis.com/attestation/status"
private val gson = Gson()

private class VerificationRejected(message: String) : RuntimeException(message)

private data class AttestationRequest(
    val challengeId: String,
    val challengeBase64Url: String,
    val certificateChainBase64Url: List<String>,
    val manifestCanonicalJson: String,
    val manifestSha256: String,
    val signatureBase64Url: String,
    val packageName: String,
    val minimumVersionCode: String,
    val signingCertificateSha256Hex: String,
)

private data class AttestationResult(
    val status: String = "verified",
    val keySecurityLevel: String,
    val verifiedBootState: String = "verified",
    val deviceLocked: Boolean = true,
    val certificateChainVerified: Boolean = true,
    val attestationChallengeMatched: Boolean = true,
    val manifestSignatureVerified: Boolean = true,
    val packageName: String,
    val packageCertificateSha256: String,
    val verifierPolicyVersion: String = "dsi-android-attestation-v1",
    val verifierLibraryCommit: String = UPSTREAM_COMMIT,
)

private data class CachedStatus(val freshUntilEpochMs: Long, val revokedSerials: Set<String>)

/** Fetches Google's status list and only reuses it for the freshness window Google publishes. */
private class GoogleAttestationStatusCache {
    @Volatile private var cached: CachedStatus? = null

    @Synchronized
    fun revokedSerials(): Set<String> {
        val now = System.currentTimeMillis()
        val current = cached
        if (current != null && current.freshUntilEpochMs > now) return current.revokedSerials
        val connection = (URI.create(STATUS_URL).toURL().openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 4_000
            readTimeout = 5_000
            instanceFollowRedirects = false
            setRequestProperty("Accept", "application/json")
            setRequestProperty("User-Agent", "Cirvanna-DSI-Attestation-Verifier/1")
        }
        try {
            if (connection.responseCode != HttpURLConnection.HTTP_OK) {
                throw IOException("Google attestation status endpoint returned HTTP ${connection.responseCode}")
            }
            if (connection.contentLengthLong > MAX_STATUS_BYTES) {
                throw IOException("Google attestation status list exceeded size limit")
            }
            val body = connection.inputStream.use { readBounded(it, MAX_STATUS_BYTES) }
            val serials = parseStatusList(body.toString(StandardCharsets.UTF_8))
            val ttl = cacheTtlMillis(connection.getHeaderField("Cache-Control"), connection.getHeaderField("Age"))
            val updated = CachedStatus(now + ttl, serials)
            cached = updated
            return serials
        } finally {
            connection.disconnect()
        }
    }
}

private fun readBounded(input: java.io.InputStream, maximumBytes: Int): ByteArray {
    val output = ByteArrayOutputStream()
    val buffer = ByteArray(8 * 1024)
    while (true) {
        val count = input.read(buffer)
        if (count < 0) break
        if (output.size() + count > maximumBytes) throw IOException("Input exceeded configured size limit")
        output.write(buffer, 0, count)
    }
    return output.toByteArray()
}

internal fun cacheTtlMillis(cacheControl: String?, ageHeader: String?): Long {
    if (cacheControl.isNullOrBlank()) return 0L
    val directives = cacheControl.split(',').map { it.trim().lowercase() }
    if (directives.any { it == "no-store" || it == "no-cache" }) return 0L
    val maxAge = directives.firstOrNull { it.startsWith("max-age=") }
        ?.substringAfter('=')?.trim()?.trim('"')?.toLongOrNull() ?: return 0L
    val age = ageHeader?.trim()?.toLongOrNull()?.coerceAtLeast(0L) ?: 0L
    return (maxAge - age).coerceIn(0L, 24L * 60L * 60L) * 1_000L
}

/** Reject every non-normal serial, including both REVOKED and SUSPENDED. */
internal fun parseStatusList(json: String): Set<String> {
    val root = JsonParser.parseString(json)
    require(root.isJsonObject) { "status list must be a JSON object" }
    val entries = root.asJsonObject.get("entries")
    require(entries != null && entries.isJsonObject) { "status list entries object missing" }
    val serials = mutableSetOf<String>()
    for ((serial, value) in entries.asJsonObject.entrySet()) {
        require(serial.matches(Regex("^[a-f0-9]+$"))) { "invalid status-list serial" }
        require(value.isJsonObject) { "invalid status-list entry" }
        val status = value.asJsonObject.get("status")
        require(status != null && status.isJsonPrimitive && status.asJsonPrimitive.isString) {
            "status-list entry is missing a status"
        }
        require(status.asString == "REVOKED" || status.asString == "SUSPENDED") {
            "unrecognized certificate status"
        }
        serials.add(serial)
    }
    return serials
}

private fun readRequest(): AttestationRequest {
    val raw = readBounded(System.`in`, MAX_REQUEST_BYTES).toString(StandardCharsets.UTF_8)
    val json = JsonParser.parseString(raw)
    require(json.isJsonObject) { "request must be a JSON object" }
    val obj = json.asJsonObject
    val allowed = setOf(
        "challengeId", "challengeBase64Url", "certificateChainBase64Url",
        "manifestCanonicalJson", "manifestSha256", "signatureBase64Url",
        "packageName", "minimumVersionCode", "signingCertificateSha256Hex",
    )
    require(obj.keySet() == allowed) { "unexpected or missing request fields" }
    val chainValue = obj.get("certificateChainBase64Url")
    require(chainValue != null && chainValue.isJsonArray) { "certificate chain missing" }
    val chain = chainValue.asJsonArray.map {
        require(it.isJsonPrimitive && it.asJsonPrimitive.isString) { "invalid certificate item" }
        it.asString
    }
    return AttestationRequest(
        challengeId = requiredString(obj, "challengeId", 128),
        challengeBase64Url = requiredString(obj, "challengeBase64Url", 43),
        certificateChainBase64Url = chain,
        manifestCanonicalJson = requiredString(obj, "manifestCanonicalJson", MAX_MANIFEST_BYTES),
        manifestSha256 = requiredString(obj, "manifestSha256", 64),
        signatureBase64Url = requiredString(obj, "signatureBase64Url", 256),
        packageName = requiredString(obj, "packageName", 200),
        minimumVersionCode = requiredString(obj, "minimumVersionCode", 32),
        signingCertificateSha256Hex = requiredString(obj, "signingCertificateSha256Hex", 64),
    )
}

private fun requiredString(obj: JsonObject, key: String, maxLength: Int): String {
    val element = obj.get(key)
    require(element != null && element.isJsonPrimitive && element.asJsonPrimitive.isString) {
        "invalid request field: $key"
    }
    val value = element.asString
    require(value.isNotBlank() && value.length <= maxLength) { "invalid request field: $key" }
    return value
}

private fun verify(request: AttestationRequest): AttestationResult {
    require(request.challengeBase64Url.matches(Regex("^[A-Za-z0-9_-]{43}$"))) { "challenge encoding invalid" }
    val challenge = Base64.getUrlDecoder().decode(request.challengeBase64Url)
    require(challenge.size == 32) { "challenge must be 256 bits" }
    require(request.manifestSha256.matches(Regex("^[a-f0-9]{64}$"))) { "manifest digest invalid" }
    require(request.packageName.matches(Regex("^[A-Za-z0-9_.]{3,200}$"))) { "package name invalid" }
    val version = request.minimumVersionCode.toBigInteger()
    require(version > BigInteger.ZERO) { "minimum version code invalid" }
    require(request.signingCertificateSha256Hex.matches(Regex("^[a-f0-9]{64}$"))) {
        "signing certificate digest invalid"
    }

    val manifestBytes = request.manifestCanonicalJson.toByteArray(StandardCharsets.UTF_8)
    require(manifestBytes.size <= MAX_MANIFEST_BYTES) { "manifest exceeds size limit" }
    require(sha256Hex(manifestBytes) == request.manifestSha256) { "manifest digest mismatch" }
    val manifestJson = JsonParser.parseString(request.manifestCanonicalJson)
    require(manifestJson.isJsonObject) { "manifest must be an object" }
    require(canonicalManifestJson(manifestJson) == request.manifestCanonicalJson) {
        "manifest is not canonical JSON"
    }
    val manifest = manifestJson.asJsonObject
    require(manifest.stringValue("schema_version") == "dsi-capture-manifest-v1") { "manifest schema mismatch" }
    require(manifest.stringValue("challenge_id") == request.challengeId) { "manifest challenge ID mismatch" }
    require(manifest.stringValue("challenge_nonce_sha256") == sha256Hex(challenge)) {
        "manifest challenge digest mismatch"
    }
    require(manifest.get("absolute_colour_measurement_approved")?.asBoolean == false) {
        "client cannot approve absolute colour measurement"
    }
    require(manifest.get("server_verification_required")?.asBoolean == true) {
        "manifest did not require server verification"
    }

    val encodedChain = request.certificateChainBase64Url
    require(encodedChain.size in 3..MAX_CHAIN_CERTIFICATES) { "certificate chain length invalid" }
    var totalBytes = 0
    val certBytes = encodedChain.map { encoded ->
        require(encoded.matches(Regex("^[A-Za-z0-9_-]+$"))) { "certificate encoding invalid" }
        val bytes = Base64.getUrlDecoder().decode(encoded)
        require(bytes.isNotEmpty() && bytes.size <= MAX_CERTIFICATE_BYTES) { "certificate size invalid" }
        totalBytes += bytes.size
        require(totalBytes <= MAX_CHAIN_BYTES) { "certificate chain exceeds size limit" }
        bytes
    }
    val factory = CertificateFactory.getInstance("X.509")
    val certificates = certBytes.map { bytes ->
        ByteArrayInputStream(bytes).use { factory.generateCertificate(it) as X509Certificate }
    }
    val expectedAppId = AttestationApplicationId(
        packages = setOf(
            AttestationPackageInfo(request.packageName, version),
        ),
        signatures = setOf(ByteString.copyFrom(request.signingCertificateSha256Hex.hexBytes())),
    )
    val statusCache = GoogleAttestationStatusCache()
    val verifier = Verifier(
        GoogleTrustAnchors,
        statusCache::revokedSerials,
        { Instant.now() },
        expectedAppId,
        ConstraintConfig(attestationApplicationId = AttestationApplicationIdConstraint.STRICT),
    )
    val result = verifier.verify(certificates, ChallengeMatcher(challenge))
    if (result !is VerificationResult.Success) {
        throw VerificationRejected("Android key-attestation proof rejected: ${result::class.simpleName}")
    }
    if (result.securityLevel != SecurityLevel.TRUSTED_ENVIRONMENT &&
        result.securityLevel != SecurityLevel.STRONG_BOX
    ) throw VerificationRejected("hardware security level rejected")
    if (result.verifiedBootState != VerifiedBootState.VERIFIED || !result.deviceLocked) {
        throw VerificationRejected("verified boot or device lock state rejected")
    }

    val signatureBytes = decodeBase64Url(request.signatureBase64Url, 128)
    val signature = Signature.getInstance("SHA256withECDSA")
    signature.initVerify(result.publicKey)
    signature.update(manifestBytes)
    if (!signature.verify(signatureBytes)) throw VerificationRejected("capture manifest signature rejected")

    val level = when (result.securityLevel) {
        SecurityLevel.STRONG_BOX -> "strongbox"
        SecurityLevel.TRUSTED_ENVIRONMENT -> "trusted_environment"
        SecurityLevel.SOFTWARE -> throw VerificationRejected("software security level rejected")
    }
    return AttestationResult(
        keySecurityLevel = level,
        packageName = request.packageName,
        packageCertificateSha256 = request.signingCertificateSha256Hex,
    )
}

private fun JsonObject.stringValue(key: String): String {
    val value = get(key)
    require(value != null && value.isJsonPrimitive && value.asJsonPrimitive.isString) {
        "manifest field missing or invalid: $key"
    }
    return value.asString
}

internal fun canonicalManifestJson(element: JsonElement): String = when {
    element.isJsonNull -> "null"
    element.isJsonArray -> element.asJsonArray.joinToString(prefix = "[", postfix = "]", separator = ",") {
        canonicalManifestJson(it)
    }
    element.isJsonObject -> element.asJsonObject.entrySet().sortedBy { it.key }
        .joinToString(prefix = "{", postfix = "}", separator = ",") {
            "${quoteCanonicalString(it.key)}:${canonicalManifestJson(it.value)}"
        }
    element.isJsonPrimitive && element.asJsonPrimitive.isString -> quoteCanonicalString(element.asString)
    element.isJsonPrimitive && element.asJsonPrimitive.isBoolean -> element.asBoolean.toString()
    element.isJsonPrimitive && element.asJsonPrimitive.isNumber -> {
        val number = BigDecimal(element.asString)
        if (number.compareTo(BigDecimal.ZERO) == 0) "0" else number.stripTrailingZeros().toPlainString()
    }
    else -> throw IllegalArgumentException("unsupported JSON value")
}

private fun quoteCanonicalString(value: String): String = buildString {
    append('"')
    value.forEach { character ->
        when (character) {
            '"' -> append("\\\"")
            '\\' -> append("\\\\")
            '\b' -> append("\\b")
            '\u000C' -> append("\\f")
            '\n' -> append("\\n")
            '\r' -> append("\\r")
            '\t' -> append("\\t")
            else -> if (character.code < 0x20) {
                append("\\u")
                append(character.code.toString(16).padStart(4, '0'))
            } else append(character)
        }
    }
    append('"')
}

private fun sha256Hex(bytes: ByteArray): String =
    MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it.toInt() and 0xff) }

private fun String.hexBytes(): ByteArray {
    require(length == 64 && matches(Regex("^[a-f0-9]+$"))) { "hex digest invalid" }
    return chunked(2).map { it.toInt(16).toByte() }.toByteArray()
}

private fun decodeBase64Url(value: String, maximumBytes: Int): ByteArray {
    require(value.matches(Regex("^[A-Za-z0-9_-]+$"))) { "base64url encoding invalid" }
    val bytes = Base64.getUrlDecoder().decode(value)
    require(bytes.isNotEmpty() && bytes.size <= maximumBytes) { "decoded signature size invalid" }
    return bytes
}

fun main() {
    try {
        print(gson.toJson(verify(readRequest())))
    } catch (_: VerificationRejected) {
        System.err.println("verification rejected")
        System.exit(2)
    } catch (_: Exception) {
        // Never log request contents, certificate material, nonce or signing data.
        System.err.println("verification unavailable or request invalid")
        System.exit(3)
    }
}
