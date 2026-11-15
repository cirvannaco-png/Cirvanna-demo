package co.cirvanna.dsi.capture

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Test

class DsiCanonicalManifestTest {
    @Test
    fun sortsObjectKeysAtEveryDepth() {
        val first = mapOf(
            "z" to 1,
            "a" to mapOf("y" to true, "b" to "value"),
        )
        val second = linkedMapOf(
            "a" to linkedMapOf("b" to "value", "y" to true),
            "z" to 1,
        )

        assertEquals(canonicalJson(first), canonicalJson(second))
        assertEquals("""{"a":{"b":"value","y":true},"z":1}""", canonicalJson(first))
    }

    @Test
    fun escapesJsonStringsWithoutPlatformJsonRuntime() {
        val value = mapOf("capture" to "quote \" slash \\ newline\n tab\t control\u0001")

        assertEquals(
            """{"capture":"quote \" slash \\ newline\n tab\t control\u0001"}""",
            canonicalJson(value),
        )
    }

    @Test
    fun canonicalHashIsStableAndChangesWhenEvidenceChanges() {
        val first = canonicalJson(mapOf("image_sha256" to "a", "lock" to true))
        val same = canonicalJson(mapOf("lock" to true, "image_sha256" to "a"))
        val changed = canonicalJson(mapOf("lock" to false, "image_sha256" to "a"))

        assertEquals(sha256Hex(first.toByteArray()), sha256Hex(same.toByteArray()))
        assertNotEquals(sha256Hex(first.toByteArray()), sha256Hex(changed.toByteArray()))
        assertEquals(
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            sha256Hex("abc".toByteArray()),
        )
    }

    @Test(expected = IllegalArgumentException::class)
    fun rejectsNonFiniteNumbersBeforeSigning() {
        canonicalJson(mapOf("lux" to Double.NaN))
    }
}
