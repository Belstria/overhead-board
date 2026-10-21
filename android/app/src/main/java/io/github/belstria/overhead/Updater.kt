package io.github.belstria.overhead

import android.app.Activity
import android.app.AlertDialog
import android.app.PendingIntent
import android.content.Intent
import android.content.pm.PackageInstaller
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import java.net.HttpURLConnection
import java.net.URL
import org.json.JSONObject

/**
 * 1.71.1: the app updates itself. Every time it is opened it asks GitHub for the newest release; when that build is
 * newer than this one it offers it (Update or Skip; 1.71.2: no waiting between checks, Skip only closes the message).
 * "Update" downloads overhead.apk and hands it to Android's installer, which asks once more (Android always does for
 * apps from outside the Play Store). Android only accepts it when it is signed with the same key as the installed app. The first time, Android asks to allow installs from Fallblatt.
 *
 * Only the web page changes most of the time and that needs no update at all: this is for the app itself
 * (notifications, widgets, camera and the like).
 */
class Updater(private val act: Activity) {
    private val main = Handler(Looper.getMainLooper())
    private var offer: Release? = null          // waiting for "allow installs from Fallblatt" in the phone's settings
    private var dialog: AlertDialog? = null
    private var busy = false

    data class Release(val build: Int, val name: String, val apk: String, val size: Long)

    private fun installed(): Int = try {
        val p = act.packageManager.getPackageInfo(act.packageName, 0)
        if (Build.VERSION.SDK_INT >= 28) p.longVersionCode.toInt() else @Suppress("DEPRECATION") p.versionCode
    } catch (e: Exception) { Int.MAX_VALUE }

    /** Looks for a newer build. [asked]: from Settings (always look, and say so when there is none). */
    fun check(asked: Boolean = false) {
        if (busy || offer != null || dialog?.isShowing == true) return
        if (installed() <= 1) return                // a local build ("dev"): nothing to compare with
        busy = true
        Thread {
            val r = latest()
            main.post {
                busy = false
                if (r == null) { if (asked) say("Couldn't reach GitHub to look for an update. Try again later."); return@post }
                if (r.build > installed()) ask(r) else if (asked) say("Fallblatt is up to date.")
            }
        }.start()
    }

    /** The newest release on GitHub: its build number (the tag android-build-N) and overhead.apk. */
    private fun latest(): Release? = try {
        val c = URL(API).openConnection() as HttpURLConnection
        c.connectTimeout = 8000
        c.readTimeout = 10000
        c.setRequestProperty("Accept", "application/vnd.github+json")
        c.setRequestProperty("User-Agent", "Fallblatt-Android")
        try {
            if (c.responseCode != 200) null else {
                val j = JSONObject(c.inputStream.bufferedReader().readText())
                val build = Regex("^android-build-(\\d+)$").find(j.optString("tag_name"))?.groupValues?.get(1)?.toInt()
                val assets = j.optJSONArray("assets")
                var apk: Release? = null
                if (build != null && assets != null) for (i in 0 until assets.length()) {
                    val a = assets.getJSONObject(i)
                    val url = a.optString("browser_download_url")
                    if (a.optString("name") == "overhead.apk" && url.startsWith(DOWNLOADS))
                        apk = Release(build, j.optString("name").removePrefix("Android app ").ifEmpty { "build $build" }, url, a.optLong("size"))
                }
                apk
            }
        } finally { c.disconnect() }
    } catch (e: Exception) { null }

    private fun ask(r: Release) {
        if (act.isFinishing) return
        dialog?.dismiss()
        val mine = try { act.packageManager.getPackageInfo(act.packageName, 0).versionName } catch (e: Exception) { "?" }
        val mb = if (r.size > 0) " (%.1f MB)".format(r.size / 1e6) else ""
        dialog = AlertDialog.Builder(act, android.R.style.Theme_Material_Dialog_Alert)
            .setTitle("Update available")
            .setMessage("Fallblatt ${r.name} is ready$mb. This phone has $mine.")
            .setPositiveButton("Update") { _, _ -> start(r) }
            .setNegativeButton("Skip", null)
            .show()
    }

    private fun say(text: String) {
        if (act.isFinishing) return
        dialog?.dismiss()
        dialog = AlertDialog.Builder(act, android.R.style.Theme_Material_Dialog_Alert)
            .setTitle("App update").setMessage(text).setPositiveButton("OK", null).show()
    }

    private fun start(r: Release) {
        if (Build.VERSION.SDK_INT >= 26 && !act.packageManager.canRequestPackageInstalls()) {
            offer = r
            dialog = AlertDialog.Builder(act, android.R.style.Theme_Material_Dialog_Alert)
                .setTitle("Allow updates")
                .setMessage("Android asks once: allow Fallblatt to install its own updates, then come back.")
                .setPositiveButton("Open settings") { _, _ ->
                    try {
                        act.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${act.packageName}")))
                    } catch (e: Exception) { offer = null; say("Couldn't open the phone's settings.") }
                }
                .setNegativeButton("Cancel") { _, _ -> offer = null }
                .show()
            return
        }
        download(r)
    }

    /** Back from the phone's settings: carry on if installs are allowed now. */
    fun resume() {
        val r = offer ?: return
        if (Build.VERSION.SDK_INT >= 26 && !act.packageManager.canRequestPackageInstalls()) return
        offer = null
        download(r)
    }

    private fun download(r: Release) {
        if (busy) return
        busy = true
        dialog?.dismiss()
        val progress = AlertDialog.Builder(act, android.R.style.Theme_Material_Dialog_Alert)
            .setTitle("Updating").setMessage("Downloading Fallblatt ${r.name} …").setCancelable(false).show()
        dialog = progress
        Thread {
            val err = try {
                val pi = act.packageManager.packageInstaller
                val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL)
                params.setAppPackageName(act.packageName)
                if (Build.VERSION.SDK_INT >= 31) params.setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_NOT_REQUIRED)
                val id = pi.createSession(params)
                pi.openSession(id).use { s ->
                    val c = URL(r.apk).openConnection() as HttpURLConnection   // GitHub sends it on to its file host (https)
                    c.connectTimeout = 10000
                    c.readTimeout = 30000
                    c.setRequestProperty("User-Agent", "Fallblatt-Android")
                    try {
                        if (c.responseCode != 200) throw Exception("HTTP ${c.responseCode}")
                        val total = c.contentLengthLong.takeIf { it > 0 } ?: r.size
                        var got = 0L
                        var shown = -1
                        s.openWrite("overhead.apk", 0, total.coerceAtLeast(-1)).use { out ->
                            c.inputStream.use { inp ->
                                val buf = ByteArray(64 * 1024)
                                while (true) {
                                    val n = inp.read(buf)
                                    if (n < 0) break
                                    out.write(buf, 0, n)
                                    got += n
                                    val pct = if (total > 0) (got * 100 / total).toInt() else -1
                                    if (pct != shown) { shown = pct; main.post { progress.setMessage("Downloading Fallblatt ${r.name} … $pct %") } }
                                }
                                s.fsync(out)
                            }
                        }
                    } finally { c.disconnect() }
                    val back = Intent(act, act.javaClass).setAction(ACTION_INSTALLED)
                    val flags = PendingIntent.FLAG_UPDATE_CURRENT or (if (Build.VERSION.SDK_INT >= 31) PendingIntent.FLAG_MUTABLE else 0)
                    s.commit(PendingIntent.getActivity(act, id, back, flags).intentSender)
                }
                null
            } catch (e: Exception) { e.message ?: "unknown error" }
            main.post {
                busy = false
                if (err != null) { progress.dismiss(); say("The update didn't download ($err). Try again later.") }
                else progress.setMessage("Installing …")
            }
        }.start()
    }

    /** Android's installer answers through MainActivity.onNewIntent; true when the intent was its answer. */
    fun handle(intent: Intent): Boolean {
        if (intent.action != ACTION_INSTALLED) return false
        dialog?.dismiss()
        when (intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)) {
            PackageInstaller.STATUS_PENDING_USER_ACTION -> {
                @Suppress("DEPRECATION")
                val confirm = intent.getParcelableExtra<Intent>(Intent.EXTRA_INTENT)
                if (confirm != null) try { act.startActivity(confirm) } catch (e: Exception) { say("Couldn't open Android's installer.") }
            }
            PackageInstaller.STATUS_SUCCESS -> {}   // Android restarts the app with the new version
            PackageInstaller.STATUS_FAILURE_ABORTED -> {}   // turned down at Android's prompt
            else -> say("Android didn't install the update: " +
                (intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE) ?: "unknown reason") + ".")
        }
        return true
    }

    fun close() { dialog?.dismiss() }

    companion object {
        const val API = "https://api.github.com/repos/Belstria/overhead-board/releases/latest"
        const val DOWNLOADS = "https://github.com/Belstria/overhead-board/releases/download/"
        const val ACTION_INSTALLED = "io.github.belstria.overhead.INSTALLED"
    }
}
