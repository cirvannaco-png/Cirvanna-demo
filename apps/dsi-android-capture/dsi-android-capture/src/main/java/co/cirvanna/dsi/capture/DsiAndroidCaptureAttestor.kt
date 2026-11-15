package co.cirvanna.dsi.capture

import android.content.Context
import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyInfo
import android.security.keystore.KeyProperties
import android.util.Base64
import com.google.android.gms.tasks.Task
import com.google.android.play.core.integrity.IntegrityManagerFactory
import com.google.android.play.core.integrity.StandardIntegrityManager
import java.nio.charset.StandardCharsets
import java.security.KeyFactory
import java.security.KeyPair
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.MessageDigest
import java.security.Signature
import java.security.spec.ECGenParameterSpec
import java.security.cert.X509Certificate
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlin.coroutines.suspendCoroutine

data class DsiAndroidAttestationEnvelope(
    val schemaVersion: String,
    val captureRef: String,
    val challengeId: String,
    val manifestSha256: String,
    val imageSha256: String,
    val manifestCanonicalJson: String,
    val signatureAlgorithm: String,
    val signatureBase64Url: String,
    val attestationCertificateChainBase64Url: List<String>,
    val playIntegrityToken: String,
    val playIntegrityRequestHash: String,
    val androidKeySecurityLevel: String,
    val verificationState: String = "pending_server_verification",
    val absoluteColourMeasurementApproved: Boolean = false,
)

/**
 * Android Keystore + Play Integrity client-side attestation candidate.
 *
 * The server must verify the certificate chain against Google's Android
 * attestation root, check the attestation challenge and revocation status,
 * verify the ECDSA signature, then decode and verify the Play Integrity token.
 * This class never marks its own output as trusted.
 */
class DsiAndroidCaptureAttestor(
    private val context: Context,
    private val cloudProjectNumber: Long,
) {
    private val integrityManager = IntegrityManagerFactory.createStandard(context)
    @Volatile
    private var tokenProvider: StandardIntegrityManager.StandardIntegrityTokenProvider? = null

    suspend fun preparePlayIntegrity() {
        if (tokenProvider != null) return
        val prepared = integrityManager.prepareIntegrityToken(
            StandardIntegrityManager.PrepareIntegrityTokenRequest.builder()
                .setCloudProjectNumber(cloudProjectNumber)
                .build(),
        ).awaitTask()
        tokenProvider = prepared
    }

    suspend fun createAttestation(
        challenge: DsiServerCaptureChallenge,
        manifest: DsiCaptureManifest,
    ): DsiAndroidAttestationEnvelope {
        val nonce = challenge.decodedNonce()
        require(manifest.challengeId == challenge.challengeId) {
            "Capture manifest and server challenge do not match"
        }

        preparePlayIntegrity()

        val alias = "dsi_capture_${sha256Hex(nonce).take(24)}"
        val keyPair = generateHardwareBackedKey(alias, nonce)
        try {
            val securityLevel = requireHardwareBackedKey(keyPair.private)
            val certificateChain = loadAttestationChain(alias)
            val canonicalBytes = manifest.canonicalJson.toByteArray(StandardCharsets.UTF_8)

            val signature = Signature.getInstance("SHA256withECDSA").run {
                initSign(keyPair.private)
                update(canonicalBytes)
                sign()
            }

            val requestHashBytes = MessageDigest.getInstance("SHA-256").digest(canonicalBytes)
            val requestHash = Base64.encodeToString(
                requestHashBytes,
                Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING,
            )
            val provider = tokenProvider
                ?: error("Play Integrity provider is not prepared")
            val integrityResponse = provider.request(
                StandardIntegrityManager.StandardIntegrityTokenRequest.builder()
                    .setRequestHash(requestHash)
                    .build(),
            ).awaitTask()

            return DsiAndroidAttestationEnvelope(
                schemaVersion = "dsi-android-attestation-v1",
                captureRef = manifest.captureRef,
                challengeId = manifest.challengeId,
                manifestSha256 = manifest.manifestSha256,
                imageSha256 = manifest.imageSha256,
                manifestCanonicalJson = manifest.canonicalJson,
                signatureAlgorithm = "SHA256withECDSA",
                signatureBase64Url = Base64.encodeToString(
                    signature,
                    Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING,
                ),
                attestationCertificateChainBase64Url = certificateChain.map { certificate ->
                    Base64.encodeToString(
                        certificate.encoded,
                        Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING,
                    )
                },
                playIntegrityToken = integrityResponse.token(),
                playIntegrityRequestHash = requestHash,
                androidKeySecurityLevel = securityLevel,
            )
        } finally {
            // The attested signing key is per-capture and is not retained.
            runCatching {
                KeyStore.getInstance("AndroidKeyStore").apply {
                    load(null)
                    deleteEntry(alias)
                }
            }
        }
    }

    private fun generateHardwareBackedKey(alias: String, challenge: ByteArray): KeyPair {
        require(Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            "Android hardware key attestation requires Android 7.0 or newer"
        }

        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        if (keyStore.containsAlias(alias)) keyStore.deleteEntry(alias)

        val spec = KeyGenParameterSpec.Builder(
            alias,
            KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY,
        )
            .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
            .setDigests(KeyProperties.DIGEST_SHA256)
            .setAttestationChallenge(challenge)
            .build()

        return KeyPairGenerator.getInstance(
            KeyProperties.KEY_ALGORITHM_EC,
            "AndroidKeyStore",
        ).run {
            initialize(spec)
            generateKeyPair()
        }
    }

    private fun requireHardwareBackedKey(privateKey: java.security.PrivateKey): String {
        val keyInfo = KeyFactory.getInstance(privateKey.algorithm, "AndroidKeyStore")
            .getKeySpec(privateKey, KeyInfo::class.java)
        val hardwareBacked = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            keyInfo.securityLevel == KeyProperties.SECURITY_LEVEL_TRUSTED_ENVIRONMENT ||
                keyInfo.securityLevel == KeyProperties.SECURITY_LEVEL_STRONGBOX
        } else {
            keyInfo.isInsideSecureHardware
        }
        check(hardwareBacked) {
            "This device does not provide a hardware-backed Android Keystore signing key"
        }
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            when (keyInfo.securityLevel) {
                KeyProperties.SECURITY_LEVEL_STRONGBOX -> "strongbox"
                KeyProperties.SECURITY_LEVEL_TRUSTED_ENVIRONMENT -> "trusted_environment"
                else -> "unknown_hardware"
            }
        } else {
            "hardware_backed_security_level_not_exposed_by_os"
        }
    }

    private fun loadAttestationChain(alias: String): List<X509Certificate> {
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        val chain = keyStore.getCertificateChain(alias)
            ?.mapNotNull { it as? X509Certificate }
            .orEmpty()
        check(chain.isNotEmpty()) {
            "Android Keystore did not return an attestation certificate chain"
        }
        return chain
    }

    private suspend fun <T> Task<T>.awaitTask(): T = suspendCoroutine { continuation ->
        addOnSuccessListener { continuation.resume(it) }
        addOnFailureListener { continuation.resumeWithException(it) }
    }
}
