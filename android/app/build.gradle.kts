plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}
// 1.70: notifications through Firebase Cloud Messaging. Its config (google-services.json) comes from the Actions secret
// GOOGLE_SERVICES_JSON at build time, never from the repository; without it the app builds without push.
val firebase = file("google-services.json").exists()
if (firebase) apply(plugin = "com.google.gms.google-services")

// The release key comes from the build machine (GitHub Actions secrets), never from the repository:
// OVERHEAD_KEYSTORE is the path to a PKCS12 file, OVERHEAD_KEYSTORE_PASSWORD its password, OVERHEAD_KEY_ALIAS the key.
val keystore: String? = System.getenv("OVERHEAD_KEYSTORE")

android {
    namespace = "io.github.belstria.overhead"
    compileSdk = 35

    defaultConfig {
        applicationId = "io.github.belstria.overhead"
        minSdk = 26
        targetSdk = 35
        versionCode = (System.getenv("VERSION_CODE") ?: "1").toInt()
        versionName = System.getenv("VERSION_NAME") ?: "dev"
    }

    signingConfigs {
        create("release") {
            if (keystore != null) {
                storeFile = file(keystore)
                storeType = "pkcs12"
                storePassword = System.getenv("OVERHEAD_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("OVERHEAD_KEY_ALIAS") ?: "overhead"
                keyPassword = System.getenv("OVERHEAD_KEYSTORE_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            // Without a key (a fork, say) the APK is signed with the throwaway debug key, so it still installs.
            signingConfig = signingConfigs.getByName(if (keystore != null) "release" else "debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    lint {
        disable += "ExpiredTargetSdkVersion"   // sideloaded, not on Google Play
    }
}

dependencies {
    implementation(platform("com.google.firebase:firebase-bom:33.5.1"))
    implementation("com.google.firebase:firebase-messaging")
}
