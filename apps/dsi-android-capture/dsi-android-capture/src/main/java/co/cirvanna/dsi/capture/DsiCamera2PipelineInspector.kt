package co.cirvanna.dsi.capture

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.ImageFormat
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.hardware.camera2.CameraMetadata
import android.util.Rational
import android.util.Size
import android.util.SizeF
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.util.Locale

/**
 * Device/camera facts returned by Android Camera2.
 *
 * These are capability observations from the platform API, not proof that a
 * capture used these controls, that OEM processing was disabled, or that the
 * camera is colour-accurate. A server-verified capture result and a lab-qualified
 * baseline are separate requirements.
 */
data class DsiCamera2PipelineSnapshot(
    val cameraId: String,
    val physicalCameraIds: List<String>,
    val manufacturer: String,
    val model: String,
    val androidRelease: String,
    val androidApiLevel: Int,
    val securityPatch: String,
    val lensFacing: String,
    val hardwareLevel: String,
    val pixelArrayWidth: Int?,
    val pixelArrayHeight: Int?,
    val physicalSensorWidthMm: Float?,
    val physicalSensorHeightMm: Float?,
    val focalLengthsMm: List<Float>,
    val colourFilterArrangement: Int?,
    val supportsRaw: Boolean,
    val supportsManualSensor: Boolean,
    val supportsManualPostProcessing: Boolean,
    val supportsAeLock: Boolean,
    val supportsAwbLock: Boolean,
    val supportsExposureTime: Boolean,
    val supportsSensorSensitivity: Boolean,
    val supportsColourCorrectionTransform: Boolean,
    val supportsColourCorrectionGains: Boolean,
    val rawOutputSizes: List<String>,
    val jpegOutputSizes: List<String>,
    val sensorCalibrationTransform1Sha256: String?,
    val sensorCalibrationTransform2Sha256: String?,
    val sensorColorTransform1Sha256: String?,
    val sensorColorTransform2Sha256: String?,
    val sensorForwardMatrix1Sha256: String?,
    val sensorForwardMatrix2Sha256: String?,
    val referenceIlluminant1: Int?,
    val referenceIlluminant2: Int?,
    val availableRequestKeys: List<String>,
    val availableResultKeys: List<String>,
    val pipelineFingerprintSha256: String,
) {
    fun toPublicEvidence(): Map<String, Any?> = mapOf(
        "schema_version" to "dsi-android-camera2-pipeline-v1",
        "camera_id" to cameraId,
        "physical_camera_ids" to physicalCameraIds,
        "manufacturer" to manufacturer,
        "model" to model,
        "android_release" to androidRelease,
        "android_api_level" to androidApiLevel,
        "security_patch" to securityPatch,
        "lens_facing" to lensFacing,
        "hardware_level" to hardwareLevel,
        "pixel_array_width" to pixelArrayWidth,
        "pixel_array_height" to pixelArrayHeight,
        "physical_sensor_width_mm" to physicalSensorWidthMm,
        "physical_sensor_height_mm" to physicalSensorHeightMm,
        "focal_lengths_mm" to focalLengthsMm,
        "colour_filter_arrangement" to colourFilterArrangement,
        "supports_raw" to supportsRaw,
        "supports_manual_sensor" to supportsManualSensor,
        "supports_manual_post_processing" to supportsManualPostProcessing,
        "supports_ae_lock" to supportsAeLock,
        "supports_awb_lock" to supportsAwbLock,
        "supports_exposure_time" to supportsExposureTime,
        "supports_sensor_sensitivity" to supportsSensorSensitivity,
        "supports_colour_correction_transform" to supportsColourCorrectionTransform,
        "supports_colour_correction_gains" to supportsColourCorrectionGains,
        "raw_output_sizes" to rawOutputSizes,
        "jpeg_output_sizes" to jpegOutputSizes,
        "sensor_calibration_transform1_sha256" to sensorCalibrationTransform1Sha256,
        "sensor_calibration_transform2_sha256" to sensorCalibrationTransform2Sha256,
        "sensor_color_transform1_sha256" to sensorColorTransform1Sha256,
        "sensor_color_transform2_sha256" to sensorColorTransform2Sha256,
        "sensor_forward_matrix1_sha256" to sensorForwardMatrix1Sha256,
        "sensor_forward_matrix2_sha256" to sensorForwardMatrix2Sha256,
        "reference_illuminant1" to referenceIlluminant1,
        "reference_illuminant2" to referenceIlluminant2,
        "available_request_keys" to availableRequestKeys,
        "available_result_keys" to availableResultKeys,
        "pipeline_fingerprint_sha256" to pipelineFingerprintSha256,
        "vendor_image_processing_state" to "not_exposed_by_camera2",
        "absolute_colour_measurement_qualified" to false,
    )
}

class DsiCamera2PipelineInspector(private val context: Context) {
    fun inspectAllCameras(): List<DsiCamera2PipelineSnapshot> {
        requireCameraPermission()
        val manager = context.getSystemService(CameraManager::class.java)
        return manager.cameraIdList.map { cameraId ->
            inspectCamera(manager, cameraId)
        }
    }

    fun inspectCamera(cameraId: String): DsiCamera2PipelineSnapshot {
        requireCameraPermission()
        val manager = context.getSystemService(CameraManager::class.java)
        require(cameraId in manager.cameraIdList) { "Unknown camera ID" }
        return inspectCamera(manager, cameraId)
    }

    private fun requireCameraPermission() {
        check(context.checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            "Camera permission must be granted by the host application"
        }
    }

    private fun inspectCamera(
        manager: CameraManager,
        cameraId: String,
    ): DsiCamera2PipelineSnapshot {
        val characteristics = manager.getCameraCharacteristics(cameraId)
        val capabilities = characteristics.get(CameraCharacteristics.REQUEST_AVAILABLE_CAPABILITIES)
            ?.toSet().orEmpty()
        val requestKeys = characteristics.get(CameraCharacteristics.REQUEST_AVAILABLE_REQUEST_KEYS)
            .orEmpty()
            .map { it.name }
            .distinct()
            .sorted()
        val resultKeys = characteristics.get(CameraCharacteristics.REQUEST_AVAILABLE_RESULT_KEYS)
            .orEmpty()
            .map { it.name }
            .distinct()
            .sorted()
        val streamMap = characteristics.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP)
        val rawSizes = streamMap?.getOutputSizes(ImageFormat.RAW_SENSOR)
            ?.map(Size::toString).orEmpty().sorted()
        val jpegSizes = streamMap?.getOutputSizes(ImageFormat.JPEG)
            ?.map(Size::toString).orEmpty().sorted()
        val pixelArray = characteristics.get(CameraCharacteristics.SENSOR_INFO_PIXEL_ARRAY_SIZE)
        val physicalSize: SizeF? = characteristics.get(CameraCharacteristics.SENSOR_INFO_PHYSICAL_SIZE)
        val focalLengths = characteristics.get(CameraCharacteristics.LENS_INFO_AVAILABLE_FOCAL_LENGTHS)
            ?.map { it.toFloat() }.orEmpty()
        val facing = when (characteristics.get(CameraCharacteristics.LENS_FACING)) {
            CameraCharacteristics.LENS_FACING_FRONT -> "front"
            CameraCharacteristics.LENS_FACING_BACK -> "rear"
            CameraCharacteristics.LENS_FACING_EXTERNAL -> "external"
            else -> "unknown"
        }
        val hardware = when (characteristics.get(CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL)) {
            CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL_LEGACY -> "legacy"
            CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL_LIMITED -> "limited"
            CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL_FULL -> "full"
            CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL_3 -> "level_3"
            CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL_EXTERNAL -> "external"
            else -> "unknown"
        }

        val transform1 = characteristics.get(CameraCharacteristics.SENSOR_CALIBRATION_TRANSFORM1)
        val transform2 = characteristics.get(CameraCharacteristics.SENSOR_CALIBRATION_TRANSFORM2)
        val colorTransform1 = characteristics.get(CameraCharacteristics.SENSOR_COLOR_TRANSFORM1)
        val colorTransform2 = characteristics.get(CameraCharacteristics.SENSOR_COLOR_TRANSFORM2)
        val forwardMatrix1 = characteristics.get(CameraCharacteristics.SENSOR_FORWARD_MATRIX1)
        val forwardMatrix2 = characteristics.get(CameraCharacteristics.SENSOR_FORWARD_MATRIX2)
        val transform1Hash = transform1?.let(::hashTransform)
        val transform2Hash = transform2?.let(::hashTransform)
        val colorTransform1Hash = colorTransform1?.let(::hashTransform)
        val colorTransform2Hash = colorTransform2?.let(::hashTransform)
        val forwardMatrix1Hash = forwardMatrix1?.let(::hashTransform)
        val forwardMatrix2Hash = forwardMatrix2?.let(::hashTransform)
        val physicalCameraIds = if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.P) {
            characteristics.physicalCameraIds.toList().sorted()
        } else {
            emptyList()
        }
        val cfa = characteristics.get(CameraCharacteristics.SENSOR_INFO_COLOR_FILTER_ARRANGEMENT)
        val refIlluminant1 = characteristics.get(CameraCharacteristics.SENSOR_REFERENCE_ILLUMINANT1)
        val refIlluminant2 = characteristics.get(CameraCharacteristics.SENSOR_REFERENCE_ILLUMINANT2)

        val snapshotFields = listOf(
            "android",
            BuildValues.manufacturer(),
            BuildValues.model(),
            cameraId,
            physicalCameraIds.joinToString(","),
            facing,
            hardware,
            BuildValues.release(),
            BuildValues.apiLevel().toString(),
            BuildValues.securityPatch(),
            pixelArray?.width?.toString().orEmpty(),
            pixelArray?.height?.toString().orEmpty(),
            physicalSize?.width?.toString().orEmpty(),
            physicalSize?.height?.toString().orEmpty(),
            focalLengths.joinToString(","),
            cfa?.toString().orEmpty(),
            capabilities.sorted().joinToString(","),
            requestKeys.joinToString(","),
            resultKeys.joinToString(","),
            rawSizes.joinToString(","),
            jpegSizes.joinToString(","),
            transform1Hash.orEmpty(),
            transform2Hash.orEmpty(),
            colorTransform1Hash.orEmpty(),
            colorTransform2Hash.orEmpty(),
            forwardMatrix1Hash.orEmpty(),
            forwardMatrix2Hash.orEmpty(),
            refIlluminant1?.toString().orEmpty(),
            refIlluminant2?.toString().orEmpty(),
            "camera2",
            "dsi-android-capture/0.1.0",
        )
        val fingerprint = sha256Hex(snapshotFields.joinToString("\n"))

        return DsiCamera2PipelineSnapshot(
            cameraId = cameraId,
            physicalCameraIds = physicalCameraIds,
            manufacturer = BuildValues.manufacturer(),
            model = BuildValues.model(),
            androidRelease = BuildValues.release(),
            androidApiLevel = BuildValues.apiLevel(),
            securityPatch = BuildValues.securityPatch(),
            lensFacing = facing,
            hardwareLevel = hardware,
            pixelArrayWidth = pixelArray?.width,
            pixelArrayHeight = pixelArray?.height,
            physicalSensorWidthMm = physicalSize?.width,
            physicalSensorHeightMm = physicalSize?.height,
            focalLengthsMm = focalLengths,
            colourFilterArrangement = cfa,
            supportsRaw = CameraMetadata.REQUEST_AVAILABLE_CAPABILITIES_RAW in capabilities,
            supportsManualSensor = CameraMetadata.REQUEST_AVAILABLE_CAPABILITIES_MANUAL_SENSOR in capabilities,
            supportsManualPostProcessing = CameraMetadata.REQUEST_AVAILABLE_CAPABILITIES_MANUAL_POST_PROCESSING in capabilities,
            supportsAeLock = CaptureKeyNames.AE_LOCK in requestKeys,
            supportsAwbLock = CaptureKeyNames.AWB_LOCK in requestKeys,
            supportsExposureTime = CaptureKeyNames.EXPOSURE_TIME in requestKeys,
            supportsSensorSensitivity = CaptureKeyNames.SENSOR_SENSITIVITY in requestKeys,
            supportsColourCorrectionTransform = CaptureKeyNames.COLOUR_TRANSFORM in requestKeys,
            supportsColourCorrectionGains = CaptureKeyNames.COLOUR_GAINS in requestKeys,
            rawOutputSizes = rawSizes,
            jpegOutputSizes = jpegSizes,
            sensorCalibrationTransform1Sha256 = transform1Hash,
            sensorCalibrationTransform2Sha256 = transform2Hash,
            sensorColorTransform1Sha256 = colorTransform1Hash,
            sensorColorTransform2Sha256 = colorTransform2Hash,
            sensorForwardMatrix1Sha256 = forwardMatrix1Hash,
            sensorForwardMatrix2Sha256 = forwardMatrix2Hash,
            referenceIlluminant1 = refIlluminant1,
            referenceIlluminant2 = refIlluminant2,
            availableRequestKeys = requestKeys,
            availableResultKeys = resultKeys,
            pipelineFingerprintSha256 = fingerprint,
        )
    }

    /**
     * Produces the exact JSON shape used by the Vision Intelligence device
     * baseline registry. This is an exact pipeline claim from Android APIs,
     * not a server-trusted identity or camera-module attestation.
     */
    fun baselineFingerprint(
        outputFormat: DsiImageOutputFormat,
        lensRole: DsiLensRole,
        colourProfileSha256: String?,
        captureAppVersion: String,
    ): Map<String, Any?> {
        require(captureAppVersion.isNotBlank())
        require(
            outputFormat !in setOf(DsiImageOutputFormat.JPEG, DsiImageOutputFormat.HEIF) ||
                colourProfileSha256?.matches(Regex("^[a-f0-9]{64}$")) == true,
        ) { "JPEG and HEIF profiles require a pinned colour-profile SHA-256" }
        if (outputFormat in setOf(DsiImageOutputFormat.RAW_SENSOR, DsiImageOutputFormat.DNG, DsiImageOutputFormat.RAW10)) {
            require(colourProfileSha256 == null) { "RAW paths cannot claim a processed output colour profile" }
        }

        val facing = when (lensFacing) {
            "front" -> "front"
            "rear" -> "rear"
            else -> "external"
        }
        require(lensRole != DsiLensRole.FRONT || facing == "front")
        require(
            lensRole !in setOf(
                DsiLensRole.REAR_WIDE,
                DsiLensRole.REAR_ULTRAWIDE,
                DsiLensRole.REAR_TELEPHOTO,
                DsiLensRole.REAR_MACRO,
            ) || facing == "rear",
        )
        require(facing != "external" || lensRole == DsiLensRole.UNKNOWN)

        return linkedMapOf(
            "platform" to "android",
            "manufacturer" to manufacturer,
            "model" to model,
            "camera_id" to cameraId,
            "physical_camera_ids" to physicalCameraIds,
            "camera_facing" to facing,
            "lens_role" to lensRole.wireValue,
            "os_release" to androidRelease,
            "platform_api_level" to androidApiLevel,
            "security_patch" to securityPatch.ifBlank { "unknown" },
            "build_fingerprint" to android.os.Build.FINGERPRINT,
            "camera_api" to "android_camera2",
            "capture_runtime" to "dsi-android-capture",
            "capture_runtime_version" to "0.1.0",
            "capture_app_version" to captureAppVersion,
            "capture_pipeline_revision" to "dsi-camera2-0.1.0",
            "output_format" to outputFormat.wireValue,
            "colour_profile_sha256" to colourProfileSha256,
            "hardware_level" to hardwareLevel,
            "pixel_array_width" to pixelArrayWidth,
            "pixel_array_height" to pixelArrayHeight,
            "physical_sensor_width_mm" to physicalSensorWidthMm?.toString(),
            "physical_sensor_height_mm" to physicalSensorHeightMm?.toString(),
            "focal_lengths_mm" to focalLengthsMm.map { it.toString() },
            "colour_filter_arrangement" to colourFilterArrangement,
            "sensor_calibration_transform1_sha256" to sensorCalibrationTransform1Sha256,
            "sensor_calibration_transform2_sha256" to sensorCalibrationTransform2Sha256,
            "sensor_color_transform1_sha256" to sensorColorTransform1Sha256,
            "sensor_color_transform2_sha256" to sensorColorTransform2Sha256,
            "sensor_forward_matrix1_sha256" to sensorForwardMatrix1Sha256,
            "sensor_forward_matrix2_sha256" to sensorForwardMatrix2Sha256,
            "reference_illuminant1" to referenceIlluminant1,
            "reference_illuminant2" to referenceIlluminant2,
            "available_request_keys" to availableRequestKeys,
            "available_result_keys" to availableResultKeys,
            "raw_output_sizes" to rawOutputSizes,
            "jpeg_output_sizes" to jpegOutputSizes,
        )
    }

    fun baselineFingerprintSha256(
        outputFormat: DsiImageOutputFormat,
        lensRole: DsiLensRole,
        colourProfileSha256: String?,
        captureAppVersion: String,
    ): String = sha256Hex(canonicalJson(baselineFingerprint(
        outputFormat,
        lensRole,
        colourProfileSha256,
        captureAppVersion,
    )).toByteArray(StandardCharsets.UTF_8))

    private fun hashTransform(transform: android.hardware.camera2.params.ColorSpaceTransform): String {
        val values = Array(9) { Rational.ZERO }
        transform.copyElements(values, 0)
        val canonical = values.joinToString(",") { "${it.numerator}/${it.denominator}" }
        return sha256Hex(canonical)
    }
}

private object CaptureKeyNames {
    const val AE_LOCK = "android.control.aeLock"
    const val AWB_LOCK = "android.control.awbLock"
    const val EXPOSURE_TIME = "android.sensor.exposureTime"
    const val SENSOR_SENSITIVITY = "android.sensor.sensitivity"
    const val COLOUR_TRANSFORM = "android.colorCorrection.transform"
    const val COLOUR_GAINS = "android.colorCorrection.gains"
}

internal object BuildValues {
    fun manufacturer(): String = android.os.Build.MANUFACTURER.orEmpty().lowercase(Locale.ROOT)
    fun model(): String = android.os.Build.MODEL.orEmpty()
    fun release(): String = android.os.Build.VERSION.RELEASE.orEmpty()
    fun apiLevel(): Int = android.os.Build.VERSION.SDK_INT
    fun securityPatch(): String = android.os.Build.VERSION.SECURITY_PATCH.orEmpty()
}

internal fun sha256Hex(value: String): String =
    MessageDigest.getInstance("SHA-256")
        .digest(value.toByteArray(StandardCharsets.UTF_8))
        .joinToString("") { "%02x".format(Locale.ROOT, it) }
