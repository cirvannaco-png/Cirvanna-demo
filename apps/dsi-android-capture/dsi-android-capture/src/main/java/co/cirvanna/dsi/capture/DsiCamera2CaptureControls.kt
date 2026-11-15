package co.cirvanna.dsi.capture

import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraMetadata
import android.hardware.camera2.CaptureRequest
import android.hardware.camera2.CaptureResult
import android.hardware.camera2.TotalCaptureResult

/**
 * Two-stage Camera2 capture control:
 *
 * 1. Enable AE/AWB and allow them to converge.
 * 2. Lock their converged settings and wait for a result that reports LOCKED.
 *
 * A request to lock is not itself evidence that the corresponding still frame
 * was captured with the locks applied. The host must attach the exact
 * TotalCaptureResult returned for the still capture to the image bytes.
 */
object DsiCamera2CaptureControls {
    /**
     * Start automatic exposure and white-balance metering with both locks off.
     * Continue repeating preview requests until [isMeteringConverged] is true.
     */
    fun applyUnlockedMetering(
        builder: CaptureRequest.Builder,
        characteristics: CameraCharacteristics,
    ) {
        val requestKeys = characteristics.getAvailableCaptureRequestKeys().toSet()
        val aeModes = characteristics
            .get(CameraCharacteristics.CONTROL_AE_AVAILABLE_MODES)
            .orEmpty()
        val awbModes = characteristics
            .get(CameraCharacteristics.CONTROL_AWB_AVAILABLE_MODES)
            .orEmpty()

        require(CaptureRequest.CONTROL_AE_LOCK in requestKeys) {
            "This camera pipeline does not expose CONTROL_AE_LOCK"
        }
        require(CaptureRequest.CONTROL_AWB_LOCK in requestKeys) {
            "This camera pipeline does not expose CONTROL_AWB_LOCK"
        }
        require(CameraMetadata.CONTROL_AE_MODE_ON in aeModes) {
            "This camera pipeline does not support automatic exposure metering"
        }
        require(CameraMetadata.CONTROL_AWB_MODE_AUTO in awbModes) {
            "This camera pipeline does not support automatic white-balance metering"
        }

        builder.set(CaptureRequest.CONTROL_MODE, CameraMetadata.CONTROL_MODE_AUTO)
        builder.set(CaptureRequest.CONTROL_SCENE_MODE, CameraMetadata.CONTROL_SCENE_MODE_DISABLED)
        builder.set(CaptureRequest.CONTROL_AE_MODE, CameraMetadata.CONTROL_AE_MODE_ON)
        builder.set(CaptureRequest.CONTROL_AWB_MODE, CameraMetadata.CONTROL_AWB_MODE_AUTO)
        builder.set(CaptureRequest.CONTROL_AE_LOCK, false)
        builder.set(CaptureRequest.CONTROL_AWB_LOCK, false)
    }

    /** True only when one capture result reports both algorithms converged. */
    fun isMeteringConverged(result: TotalCaptureResult): Boolean {
        return result.get(CaptureResult.CONTROL_AE_STATE) ==
            CameraMetadata.CONTROL_AE_STATE_CONVERGED &&
            result.get(CaptureResult.CONTROL_AWB_STATE) ==
            CameraMetadata.CONTROL_AWB_STATE_CONVERGED
    }

    /**
     * Lock the converged metering values after [isMeteringConverged] has passed.
     * If the camera does not support these controls, this throws rather than
     * downgrading silently to an uncalibrated capture.
     */
    fun applyLocksAfterConvergence(
        builder: CaptureRequest.Builder,
        characteristics: CameraCharacteristics,
        convergedResult: TotalCaptureResult,
    ) {
        require(isMeteringConverged(convergedResult)) {
            "AE and AWB must both be converged before their values are locked"
        }
        val requestKeys = characteristics.getAvailableCaptureRequestKeys().toSet()
        require(CaptureRequest.CONTROL_AE_LOCK in requestKeys) {
            "This camera pipeline does not expose CONTROL_AE_LOCK"
        }
        require(CaptureRequest.CONTROL_AWB_LOCK in requestKeys) {
            "This camera pipeline does not expose CONTROL_AWB_LOCK"
        }

        builder.set(CaptureRequest.CONTROL_AE_LOCK, true)
        builder.set(CaptureRequest.CONTROL_AWB_LOCK, true)
    }

    /** Inspect the actual result for the capture frame to be bound to image bytes. */
    fun observeLockResult(result: TotalCaptureResult): DsiCaptureLockObservation {
        val request = result.request
        val requestedAeLock = request.get(CaptureRequest.CONTROL_AE_LOCK) == true
        val requestedAwbLock = request.get(CaptureRequest.CONTROL_AWB_LOCK) == true
        val aeState = result.get(CaptureResult.CONTROL_AE_STATE)
        val awbState = result.get(CaptureResult.CONTROL_AWB_STATE)
        val observedAeLock = result.get(CaptureResult.CONTROL_AE_LOCK) == true
        val observedAwbLock = result.get(CaptureResult.CONTROL_AWB_LOCK) == true

        return DsiCaptureLockObservation(
            exposureLockRequested = requestedAeLock,
            exposureLockObserved = requestedAeLock && observedAeLock &&
                aeState == CameraMetadata.CONTROL_AE_STATE_LOCKED,
            exposureStateCode = aeState,
            whiteBalanceLockRequested = requestedAwbLock,
            whiteBalanceLockObserved = requestedAwbLock && observedAwbLock &&
                awbState == CameraMetadata.CONTROL_AWB_STATE_LOCKED,
            whiteBalanceStateCode = awbState,
            appliedExposureTimeNs = result.get(CaptureResult.SENSOR_EXPOSURE_TIME),
            appliedSensitivityIso = result.get(CaptureResult.SENSOR_SENSITIVITY),
            sensorTimestampNs = result.get(CaptureResult.SENSOR_TIMESTAMP),
        )
    }
}

data class DsiCaptureLockObservation(
    val exposureLockRequested: Boolean,
    val exposureLockObserved: Boolean,
    val exposureStateCode: Int?,
    val whiteBalanceLockRequested: Boolean,
    val whiteBalanceLockObserved: Boolean,
    val whiteBalanceStateCode: Int?,
    val appliedExposureTimeNs: Long?,
    val appliedSensitivityIso: Int?,
    val sensorTimestampNs: Long?,
) {
    val bothLocksObserved: Boolean
        get() = exposureLockObserved && whiteBalanceLockObserved
}
