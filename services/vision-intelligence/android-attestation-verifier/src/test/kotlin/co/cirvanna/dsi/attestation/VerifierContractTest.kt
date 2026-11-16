package co.cirvanna.dsi.attestation

import com.google.gson.JsonParser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFails

class VerifierContractTest {
    @Test
    fun canonicalJsonSortsKeysAndNormalizesNumbers() {
        val parsed = JsonParser.parseString("""{"z":1.0,"a":{"d":1e-6,"b":true}}""")
        assertEquals("""{"a":{"b":true,"d":0.000001},"z":1}""", canonicalManifestJson(parsed))
    }

    @Test
    fun revocationListRejectsRevokedAndSuspendedSerials() {
        val result = parseStatusList(
            """{"entries":{"1a":{"status":"REVOKED"},"2b":{"status":"SUSPENDED"}}}"""
        )
        assertEquals(setOf("1a", "2b"), result)
    }

    @Test
    fun revocationListRejectsUnknownStatuses() {
        assertFails { parseStatusList("""{"entries":{"1a":{"status":"GOOD"}}}""") }
    }

    @Test
    fun revocationCacheHonoursAgeAndNoCacheDirectives() {
        assertEquals(50_000L, cacheTtlMillis("public, max-age=60", "10"))
        assertEquals(0L, cacheTtlMillis("no-cache, max-age=300", "0"))
        assertEquals(0L, cacheTtlMillis("public", "0"))
        assertEquals(0L, cacheTtlMillis("public, max-age=120", "180"))
    }
}
