pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        maven { url = uri("/tmp/keyattestation-m2repo") }
        mavenCentral()
        google()
    }
}

rootProject.name = "dsi-android-attestation-verifier"
