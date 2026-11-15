package co.cirvanna.dsi.capture

import android.hardware.camera2.CaptureRequest
import android.hardware.camera2.CaptureResult
import android.hardware.camera2.TotalCaptureResult
import android.hardware.camera2.params.ColorSpaceTransform
import android.hardware.camera2.params.RggbChannelVector
import android.util.Base64
import android.util.Rational
import org.json.JSONObject
import java.math.BigDecimal
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.util.UUID

enum class DsiCaptureMode(val wireValue: String) {
    CONTROLLED_DIFFUSE("controlled_diffuse"),
    CROSS_POLARIZED("cross_polarized"),
    AMBIENT_RELATIVE("ambient_relative"),
}

enum class DsiImageOutputFormat(val wireValue: String) {
    RAW_SENSOR("raw_sensor"),
    JPEG("jpeg"),
    YUV_420_888("yuv_420_888"),
    HEIF("heif"),
    DNG("dng"),
}

enum class DsiChartCondition(val wireValue: String) {
    GOOD("good"),
    WORN("worn"),
    UNKNOWN("unknown"),
    NOT_PRESENT("not_present"),
}

data class DsiServerCaptureChallenge(
    val challengeId: String,
    /** Base64url-encoded, server-generated, single-use random nonce (at least 32 bytes). */
    val nonceBase64Url: String,
    val expiresAtEpochMs: Long,
) {
    fun decodedNonce(): ByteArray {
        require(challengeId.length in 8..128) { "Invalid server challenge ID" }
        require(System.currentTimeMillis() < expiresAtEpochMs) { "Server capture challenge has expired" }
        val decoded = Base64.decode(
            nonceBase64Url,
            Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING,
        )
        require(decoded.size >= 32) { "Server capture nonce must contain at least 256 bits" }
        return decoded
    }
}

data class DsiIlluminationDeclaration(
    val profile: String,
    val reportedIlluminant: String?,
    val reportedIlluminanceLux: Double?,
    val calibratedMeterModel: String?,
    val meterCalibrationReference: String?,
) {
    init {
        require(profile.isNotBlank())
        require(reportedIlluminanceLux == null || reportedIlluminanceLux >= 0.0)
        if (calibratedMeterModel != null || meterCalibrationReference != null) {
            require(!calibratedMeterModel.isNullOrBlank())
            require(!meterCalibrationReference.isNullOrBlank())
            require(reportedIlluminanceLux != null) {
                "A calibrated meter declaration requires a lux reading"
            }
        }
    }
}

data class DsiChartDeclaration(
    val condition: DsiChartCondition,
    val profileId: String?,
    val profileSha256: String?,
    val productionEdition: String?,
) {
    init {
        if (condition == DsiChartCondition.NOT_PRESENT) {
            require(profileId == null && profileSha256 == null)
        } else {
            require(!profileId.isNullOrBlank())
            require(profileSha256?.matches(Regex("^[a-f0-9]{64}$")) == true)
        }
    }
}

data class DsiPolarizationDeclaration(
    val lightSourcePolarizerReference: String,
    val cameraAnalyzerReference: String,
    val relativeOrientationDegrees: Double,
    val opticalSetupReference: String,
) {
    init {
        require(lightSourcePolarizerReference.isNotBlank())
        require(cameraAnalyzerReference.isNotBlank())
        require(relativeOrientationDegrees in 0.0..180.0)
        require(opticalSetupReference.length >= 8)
    }
}

data class DsiCaptureManifestInput(
    val challenge: DsiServerCaptureChallenge,
    val cameraPipeline: DsiCamera2PipelineSnapshot,
    val captureResult: TotalCaptureResult,
    /** Kept in memory only. This library hashes the bytes and never writes them. */
    val imageBytes: ByteArray,
    val outputFormat: DsiImageOutputFormat,
    val captureMode: DsiCaptureMode,
    val illumination: DsiIlluminationDeclaration,
    val chart: DsiChartDeclaration,
    val polarization: DsiPolarizationDeclaration? = null,
    val captureRef: String = "cap_${UUID.randomUUID()}",
    val appRuntimeVersion: String = "0.1.0",
)

/**
 * A canonical manifest over the exact image digest and Camera2 result.
 *
 * This is still client-generated evidence. The server must verify the one-time
 * nonce, hardware key-attestation chain, signature and Play Integrity token
 * before trusting it. It must never promote an absolute colour measurement.
 */
data class DsiCaptureManifest(
    val canonicalJson: String,
    val manifestSha256: String,
    val imageSha256: String,
    val imageByteCount: Int,
    val captureRef: String,
    val challengeId: String,
    val observedExposureLock: Boolean,
    val observedWhiteBalanceLock: Boolean,
) {
    companion object {
        private const val MAX_IMAGE_BYTES = 32 * 1024 * 1024

        fun create(input: DsiCaptureManifestInput): DsiCaptureManifest {
            require(input.imageBytes.isNotEmpty()) { "Capture image is empty" }
            require(input.imageBytes.size <= MAX_IMAGE_BYTES) { "Capture image exceeds SDK limit" }
            require(input.captureRef.matches(Regex("^cap_[A-Za-z0-9_-]{12,96}$"))) {
                "Capture reference must be opaque and non-identifying"
            }
            require(input.appRuntimeVersion.isNotBlank())
            require(
                (input.captureMode == DsiCaptureMode.CROSS_POLARIZED) ==
                    (input.polarization != null),
            ) { "Cross-polarized captures require an optical setup declaration only for that mode" }

            val nonce = input.challenge.decodedNonce()
            val result = input.captureResult
            val lockObservation = DsiCamera2CaptureControls.observeLockResult(result)
            val imageDigest = sha256Hex(input.imageBytes)
            val nonceDigest = sha256Hex(nonce)
            val captureTimestamp = result.get(CaptureResult.SENSOR_TIMESTAMP)

            val fields = linkedMapOf<String, Any?>(
                "schema_version" to "dsi-capture-manifest-v1",
                "capture_ref" to input.captureRef,
                "challenge_id" to input.challenge.challengeId,
                "challenge_nonce_sha256" to nonceDigest,
                "challenge_expires_at_epoch_ms" to input.challenge.expiresAtEpochMs,
                "capture_wall_clock_epoch_ms" to System.currentTimeMillis(),
                "capture_sensor_timestamp_ns" to captureTimestamp,
                "image_sha256" to imageDigest,
                "image_byte_count" to input.imageBytes.size,
                "output_format" to input.outputFormat.wireValue,
                "capture_mode" to input.captureMode.wireValue,
                "app_runtime_version" to input.appRuntimeVersion,
                "device_pipeline_fingerprint_sha256" to input.cameraPipeline.pipelineFingerprintSha256,
                "camera_pipeline" to input.cameraPipeline.toPublicEvidence(),
                "illumination_declaration" to mapOf(
                    "profile" to input.illumination.profile,
                    "reported_illuminant" to input.illumination.reportedIlluminant,
                    "reported_illuminance_lux" to input.illumination.reportedIlluminanceLux,
                    "calibrated_meter_model" to input.illumination.calibratedMeterModel,
                    "meter_calibration_reference" to input.illumination.meterCalibrationReference,
                    "evidence_kind" to "client_declaration_not_independently_attested",
                ),
                "chart_declaration" to mapOf(
                    "condition" to input.chart.condition.wireValue,
                    "profile_id" to input.chart.profileId,
                    "profile_sha256" to input.chart.profileSha256,
                    "production_edition" to input.chart.productionEdition,
                    "evidence_kind" to "client_declaration_not_independently_attested",
                ),
                "polarization_declaration" to input.polarization?.let {
                    mapOf(
                        "light_source_polarizer_reference" to it.lightSourcePolarizerReference,
                        "camera_analyzer_reference" to it.cameraAnalyzerReference,
                        "relative_orientation_degrees" to it.relativeOrientationDegrees,
                        "optical_setup_reference" to it.opticalSetupReference,
                        "evidence_kind" to "client_declaration_not_independently_attested",
                    )
                },
                "capture_request" to mapOf(
                    "ae_lock_requested" to lockObservation.exposureLockRequested,
                    "awb_lock_requested" to lockObservation.whiteBalanceLockRequested,
                    "scene_mode" to result.request.get(CaptureRequest.CONTROL_SCENE_MODE),
                    "ae_mode" to result.request.get(CaptureRequest.CONTROL_AE_MODE),
                    "awb_mode" to result.request.get(CaptureRequest.CONTROL_AWB_MODE),
                ),
                "capture_result" to mapOf(
                    "ae_lock_observed" to lockObservation.exposureLockObserved,
                    "ae_state_code" to lockObservation.exposureStateCode,
                    "awb_lock_observed" to lockObservation.whiteBalanceLockObserved,
                    "awb_state_code" to lockObservation.whiteBalanceStateCode,
                    "exposure_time_ns" to lockObservation.appliedExposureTimeNs,
                    "sensitivity_iso" to lockObservation.appliedSensitivityIso,
                    "sensor_timestamp_ns" to lockObservation.sensorTimestampNs,
                    "colour_correction_gains" to gainsToMap(
                        result.get(CaptureResult.COLOR_CORRECTION_GAINS),
                    ),
                    "colour_correction_transform_sha256" to transformSha256(
                        result.get(CaptureResult.COLOR_CORRECTION_TRANSFORM),
                    ),
                ),
                "vendor_image_processing_state" to "not_exposed_by_camera2",
                "absolute_colour_measurement_approved" to false,
                "server_verification_required" to true,
                "raw_image_persisted_by_sdk" to false,
            )

            val canonical = canonicalJson(fields)
            return DsiCaptureManifest(
                canonicalJson = canonical,
                manifestSha256 = sha256Hex(canonical.toByteArray(StandardCharsets.UTF_8)),
                imageSha256 = imageDigest,
                imageByteCount = input.imageBytes.size,
                captureRef = input.captureRef,
                challengeId = input.challenge.challengeId,
                observedExposureLock = lockObservation.exposureLockObserved,
                observedWhiteBalanceLock = lockObservation.whiteBalanceLockObserved,
            )
        }

        private fun gainsToMap(gains: RggbChannelVector?): Map<String, Float>? = gains?.let {
            mapOf(
                "red" to it.red,
                "green_even" to it.greenEven,
                "green_odd" to it.greenOdd,
                "blue" to it.blue,
            )
        }

        private fun transformSha256(transform: ColorSpaceTransform?): String? {
            transform ?: return null
            val values = Array(9) { Rational.ZERO }
            transform.copyElements(values, 0)
            val canonical = values.joinToString(",") { "${it.numerator}/${it.denominator}" }
            return sha256Hex(canonical)
        }
    }
}

/** Stable JSON encoding: object keys are sorted recursively and numbers are normalized. */
internal fun canonicalJson(value: Any?): String = when (value) {
    null -> "null"
    is String -> JSONObject.quote(value)
    is Boolean -> value.toString()
    is Int, is Long, is Short, is Byte -> value.toString()
    is Float, is Double -> {
        val number = (value as Number).toDouble()
        require(number.isFinite()) { "Non-finite numbers are not allowed in a signed capture manifest" }
        BigDecimal(number.toString()).stripTrailingZeros().toPlainString()
    }
    is Number -> BigDecimal(value.toString()).stripTrailingZeros().toPlainString()
    is Map<*, *> -> value.entries
        .associate { (key, entryValue) ->
            require(key is String) { "Canonical JSON map keys must be strings" }
            key to entryValue
        }
        .toSortedMap()
        .entries
        .joinToString(prefix = "{", postfix = "}", separator = ",") {
            "${JSONObject.quote(it.key)}:${canonicalJson(it.value)}"
        }
    is Iterable<*> -> value.joinToString(prefix = "[", postfix = "]", separator = ",") {
        canonicalJson(it)
    }
    else -> error("Unsupported canonical JSON value type: ${value::class.java.name}")
}

internal fun sha256Hex(bytes: ByteArray): String =
    MessageDigest.getInstance("SHA-256")
        .digest(bytes)
        .joinToString("") { "%02x".format(it.toInt() and 0xff) }
