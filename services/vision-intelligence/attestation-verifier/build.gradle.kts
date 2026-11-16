plugins {
    id("org.jetbrains.kotlin.jvm") version "2.2.0"
    application
}

dependencies {
    implementation("com.android.keyattestation:keyattestation:0.1-SNAPSHOT")
    implementation("com.google.code.gson:gson:2.11.0")
}

kotlin {
    jvmToolchain(21)
}

application {
    mainClass.set("co.cirvanna.dsi.attestation.MainKt")
}

tasks.register<Jar>("fatJar") {
    archiveFileName.set("dsi-android-attestation-verifier.jar")
    duplicatesStrategy = DuplicatesStrategy.EXCLUDE
    manifest {
        attributes["Main-Class"] = application.mainClass.get()
    }
    from(sourceSets.main.get().output)
    dependsOn(configurations.runtimeClasspath)
    from({
        configurations.runtimeClasspath.get()
            .filter { it.name.endsWith(".jar") }
            .map { zipTree(it) }
    })
}
