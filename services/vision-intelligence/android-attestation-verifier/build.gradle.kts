plugins {
    kotlin("jvm") version "2.2.0"
    application
}

dependencies {
    implementation("com.android.keyattestation:keyattestation:0.1-SNAPSHOT")
    implementation("com.google.code.gson:gson:2.11.0")
    testImplementation(kotlin("test-junit5"))
    testRuntimeOnly("org.junit.jupiter:junit-jupiter-engine:5.10.2")
}

kotlin {
    jvmToolchain(21)
}

application {
    mainClass.set("co.cirvanna.dsi.attestation.MainKt")
}

tasks.test {
    useJUnitPlatform()
}
