pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "cirvanna-dsi-android-attestation-verifier"

includeBuild("vendor/android-keyattestation") {
    dependencySubstitution {
        substitute(module("com.android.keyattestation:keyattestation")).using(project(":"))
    }
}
