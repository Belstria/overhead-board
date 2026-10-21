package io.github.belstria.overhead

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.content.res.Configuration
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.CancellationSignal
import android.os.Handler
import android.os.Looper
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.view.WindowManager
import android.webkit.JavascriptInterface
import android.webkit.RenderProcessGoneDetail
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.TextView
import java.net.HttpURLConnection
import java.net.Inet4Address
import java.net.NetworkInterface
import java.net.URL
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicReference
import org.json.JSONObject

/**
 * The Overhead app: the relay's phone page (/app/) full screen. Everything on the page comes from the relay on the
 * home computer, so the app is always the current version; this activity only finds the relay and shows the page.
 *
 * On first start it looks for the relay on the Wi-Fi (every address of the phone's /24 network, port 8080, asking
 * /health and checking the relay's Server header). If it can't find one, or the saved relay doesn't answer, it asks
 * for the address. The page's Settings → About → Change relay calls [Bridge.changeRelay], and Settings → Use current
 * location calls [Bridge.locate], which answers through window.__overheadHere(lat, lon, accuracy, error).
 *
 * Turned on its side, the page takes its landscape layout (the page itself does that) and the app goes full screen.
 * While the app is open the screen stays on (Android lets it time out again once the app is left).
 */
class MainActivity : Activity() {
    private lateinit var root: FrameLayout
    private lateinit var web: WebView              // the phone page
    private var webReady = false
    private var locateFrom: WebView? = null
    private lateinit var note: TextView
    private val main = Handler(Looper.getMainLooper())
    private val prefs by lazy { getSharedPreferences("overhead", MODE_PRIVATE) }
    private var relay: String? = null
    private var failed = false
    private var searching = false
    private var dialog: AlertDialog? = null
    private var handover = 0
    private var camAsk: android.webkit.PermissionRequest? = null   // Sky view's camera request, while Android asks
    private val updater by lazy { Updater(this) }   // 1.71.1: the app's own updates from GitHub

    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        root = FrameLayout(this)
        root.setBackgroundColor(BG)
        web = newWeb()
        note = TextView(this)
        note.setTextColor(INK)
        note.textSize = 17f
        note.gravity = Gravity.CENTER
        note.setPadding(64, 64, 64, 64)
        root.addView(web, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))
        root.addView(note, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))
        setContentView(root)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)   // a board doesn't go dark: on as long as the app is open
        // Upright, the page keeps clear of the status bar, the navigation bar and the camera cutout (Android 15 draws edge
        // to edge). On its side (full screen) it fills the whole screen, under the camera too, and is told how far the
        // cutout reaches (--cut-l, --cut-r) to keep its flaps clear of it.
        if (Build.VERSION.SDK_INT >= 28) window.attributes = window.attributes.also {
            it.layoutInDisplayCutoutMode = if (Build.VERSION.SDK_INT >= 30) WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_ALWAYS
                                           else WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES
        }
        root.setOnApplyWindowInsetsListener { v, insets ->
            val side = landscape()
            if (Build.VERSION.SDK_INT >= 30) {
                val b = insets.getInsets(WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout())
                val cut = insets.getInsets(WindowInsets.Type.displayCutout())
                if (side) v.setPadding(0, 0, 0, 0) else v.setPadding(b.left, b.top, b.right, b.bottom)
                cutL = if (side) cut.left else 0
                cutR = if (side) cut.right else 0
            } else {
                val cut = if (Build.VERSION.SDK_INT >= 28) insets.displayCutout else null
                @Suppress("DEPRECATION")
                if (side) v.setPadding(0, 0, 0, 0)
                else v.setPadding(insets.systemWindowInsetLeft, insets.systemWindowInsetTop, insets.systemWindowInsetRight, insets.systemWindowInsetBottom)
                cutL = if (side && Build.VERSION.SDK_INT >= 28) cut?.safeInsetLeft ?: 0 else 0
                cutR = if (side && Build.VERSION.SDK_INT >= 28) cut?.safeInsetRight ?: 0 else 0
            }
            pushCut()
            insets
        }
        // The relay's https address (the tunnel) once the page has handed it over: TLS proves it is this relay, wherever
        // the phone is. The address on the Wi-Fi is the fallback when the internet is down.
        val pub = prefs.getString(PUBLIC, null)
        val saved = prefs.getString(KEY, null)
        if (pub != null) open(pub) else if (saved != null) open(saved) else search()
        applyOrientation()
    }

    private var cutL = 0
    private var cutR = 0

    /** Tells the page how far the camera cutout reaches into the screen at the sides, in CSS pixels. */
    private fun pushCut() {
        if (!webReady) return
        val d = resources.displayMetrics.density
        val css = "document.documentElement.style"
        web.evaluateJavascript("$css.setProperty('--cut-l','${cutL / d}px');$css.setProperty('--cut-r','${cutR / d}px');" +
            "dispatchEvent(new Event('resize'))", null)
    }

    private fun newWeb(): WebView {
        val view = WebView(this)
        view.setBackgroundColor(BG)
        view.visibility = View.INVISIBLE
        setUpWeb(view)
        return view
    }

    private fun setUpWeb(view: WebView) {
        val s = view.settings
        s.javaScriptEnabled = true
        s.domStorageEnabled = true                  // the page keeps its settings in localStorage
        s.mediaPlaybackRequiresUserGesture = false  // flap sound and chimes
        s.minimumFontSize = 1                       // the page sizes its own small print (Settings' engraving):
        s.minimumLogicalFontSize = 1                // Android's minimum text size would make it overflow
        s.textZoom = 100
        val version = try { packageManager.getPackageInfo(packageName, 0).versionName } catch (e: Exception) { "?" }
        s.userAgentString = "${s.userAgentString} OverheadAndroid/$version"   // the relay lists the phone as the app
        view.addJavascriptInterface(Bridge(view), "OverheadAndroid")
        // 1.70.2: Sky view asks for the camera; the WebView passes that on to Android (asked the first time) and grants it
        // to the relay's own page only.
        view.webChromeClient = object : WebChromeClient() {
            override fun onPermissionRequest(request: android.webkit.PermissionRequest) {
                main.post {
                    val cam = android.webkit.PermissionRequest.RESOURCE_VIDEO_CAPTURE
                    if (cam !in request.resources || relay == null || request.origin.host != Uri.parse(relay).host) { request.deny(); return@post }
                    if (checkSelfPermission(Manifest.permission.CAMERA) == android.content.pm.PackageManager.PERMISSION_GRANTED) request.grant(arrayOf(cam))
                    else { camAsk?.deny(); camAsk = request; requestPermissions(arrayOf(Manifest.permission.CAMERA), REQ_CAMERA) }
                }
            }
        }
        view.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val url = request.url
                if (relay != null && url.host == Uri.parse(relay).host) return false
                // Links away from the relay (photo credits, the big board's sources) open in the browser.
                try { startActivity(Intent(Intent.ACTION_VIEW, url)) } catch (e: Exception) { }
                return true
            }

            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                if (!request.isForMainFrame) return
                val lan = prefs.getString(KEY, null)
                if (relay == prefs.getString(PUBLIC, null) && lan != null && lan != relay) {
                    handover = 0
                    open(lan)                       // no internet: the relay on the home Wi-Fi
                    return
                }
                failed = true
                web.visibility = View.INVISIBLE
                showNote("Can't reach the relay at $relay.")
                askAddress("Can't reach the relay at $relay. Is the computer on, the relay running, and this phone on the home Wi-Fi?")
            }

            // Away for a while, Android may end the page's renderer to free memory. Without this the app stayed black
            // (or closed): a fresh WebView takes the old one's place and loads the page again.
            override fun onRenderProcessGone(view: WebView, detail: RenderProcessGoneDetail): Boolean {
                if (view !== web) return true
                root.removeView(view)
                view.destroy()
                if (locateFrom === view) locateFrom = null
                web = newWeb()
                root.addView(web, 0, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))
                relay?.let { open(it) } ?: search()
                return true
            }

            override fun onPageFinished(view: WebView, url: String) {
                if (url.startsWith("about:")) return
                if (failed) return
                if (handover > 0 && Uri.parse(url).path.orEmpty().startsWith("/join/")) {
                    if (handover++ == 1) view.evaluateJavascript("document.forms[0] && document.forms[0].submit()", null)
                    else {                          // the link didn't take: stay with the Wi-Fi address
                        handover = 0
                        prefs.edit().remove(PUBLIC).apply()
                        prefs.getString(KEY, null)?.let { open(it) }
                    }
                    return
                }
                handover = 0
                if (url.contains("/app/") || url.contains("/light/")) prefs.edit().putString(LIVE, relay).apply()   // 1.69: the widgets use it
                webReady = true
                applyOrientation()
                pushCut()
            }
        }
    }

    private fun showNote(text: String) {
        note.text = text
        note.visibility = View.VISIBLE
    }

    private fun open(base: String) {
        relay = base
        failed = false
        webReady = false
        showNote("Connecting to $base …")
        val path = intent?.getStringExtra(OPEN_URL)?.takeIf { it.startsWith("/") && !it.startsWith("//") } ?: "/app/"
        intent?.removeExtra(OPEN_URL)
        web.loadUrl(base + path)
    }

    /** 1.70: a tapped notification opens its page (the app may be open already). */
    override fun onNewIntent(next: Intent) {
        super.onNewIntent(next)
        if (updater.handle(next)) return
        setIntent(next)
        val path = next.getStringExtra(OPEN_URL)?.takeIf { it.startsWith("/") && !it.startsWith("//") } ?: return
        next.removeExtra(OPEN_URL)
        relay?.let { web.loadUrl(it + path) }
    }

    /** 1.70: notifications: Android 13+ asks first, then Firebase gives this phone's token, which goes to the page. */
    private fun pushFetch() {
        val answer = { tok: String, err: String ->
            main.post { web.evaluateJavascript("window.fallblattPush && fallblattPush(${JSONObject.quote(tok)}, ${JSONObject.quote(err)})", null) }
        }
        try {
            com.google.firebase.messaging.FirebaseMessaging.getInstance().token.addOnCompleteListener { t ->
                if (t.isSuccessful && t.result != null) {
                    prefs.edit().putString(PushService.TOKEN, t.result).apply()
                    answer(t.result, "")
                } else answer("", "Firebase didn't answer. Try again in a moment.")
            }
        } catch (e: Exception) {
            answer("", "This build of the app has no notifications.")
        }
    }

    /* ---------- on its side: the same page in its landscape layout, full screen ---------- */

    private fun landscape() = resources.configuration.orientation == Configuration.ORIENTATION_LANDSCAPE

    private fun applyOrientation() {
        if (webReady && !failed) { web.visibility = View.VISIBLE; note.visibility = View.GONE }
        immersive(landscape())
    }

    private fun immersive(on: Boolean) {
        if (Build.VERSION.SDK_INT >= 30) {
            val c = window.insetsController ?: return
            if (on) {
                c.systemBarsBehavior = WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
                c.hide(WindowInsets.Type.systemBars())
            } else c.show(WindowInsets.Type.systemBars())
        } else {
            @Suppress("DEPRECATION")
            window.decorView.systemUiVisibility = if (on) View.SYSTEM_UI_FLAG_FULLSCREEN or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or
                View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY or View.SYSTEM_UI_FLAG_LAYOUT_STABLE else 0
        }
    }

    override fun onConfigurationChanged(newConfig: Configuration) {
        super.onConfigurationChanged(newConfig)
        applyOrientation()
        root.requestApplyInsets()                   // padding and the cutout differ upright and on its side
    }

    private fun use(base: String) {
        val e = prefs.edit().putString(KEY, base)
        if (base != prefs.getString(PUBLIC, null)) e.remove(PUBLIC)   // typed or found by hand: that one, not the https one
        e.apply()
        open(base)
    }

    private fun search() {
        if (searching) return
        searching = true
        dialog?.dismiss()
        web.visibility = View.INVISIBLE
        showNote("Looking for the relay on this Wi-Fi …")
        Thread {
            val found = findRelay()
            main.post {
                searching = false
                if (found != null) use(found)
                else {
                    showNote("No relay found on this Wi-Fi.")
                    askAddress("No relay found on this Wi-Fi. Is the computer on and the relay running? You can also type its address.")
                }
            }
        }.start()
    }

    private fun askAddress(message: String?) {
        if (isFinishing || searching) return
        dialog?.dismiss()
        val input = EditText(this)
        input.inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
        input.setText(relay ?: "http://")
        input.setSelection(input.text.length)
        val box = FrameLayout(this)
        box.setPadding(56, 16, 56, 0)
        box.addView(input)
        val loaded = !failed && relay != null && webReady
        dialog = AlertDialog.Builder(this, android.R.style.Theme_Material_Dialog_Alert)
            .setTitle("Relay")
            .setMessage((if (message != null) "$message\n\n" else "") +
                "The relay prints its address when it starts, such as http://192.168.1.20:8080")
            .setView(box)
            .setCancelable(loaded)
            .setPositiveButton("Connect") { _, _ ->
                val url = normalize(input.text.toString())
                if (url == null) askAddress("That isn't an address.") else use(url)
            }
            .setNeutralButton("Search") { _, _ -> search() }
            .setNegativeButton(if (loaded) "Cancel" else "Close") { _, _ -> if (!loaded) finish() }
            .show()
    }

    /** "192.168.1.20", "192.168.1.20:8080/app/" or "http://pc:8080" → "http://192.168.1.20:8080". */
    private fun normalize(text: String): String? {
        var t = text.trim().trimEnd('/')
        if (t.endsWith("/app")) t = t.removeSuffix("/app")
        if (!t.contains("://")) t = "http://$t"
        val u = Uri.parse(t)
        val host = u.host ?: return null
        if (host.isEmpty() || u.scheme !in listOf("http", "https")) return null
        val port = if (u.port > 0) u.port else if (u.scheme == "https") 443 else PORT
        return "${u.scheme}://$host:$port"
    }

    /** The relay on this phone's network: every address of its /24, asked for /health at once. */
    private fun findRelay(): String? {
        val me = wifiAddress() ?: return null
        val b = me.address
        val prefix = "${b[0].toInt() and 255}.${b[1].toInt() and 255}.${b[2].toInt() and 255}."
        val found = AtomicReference<String?>(null)
        val left = CountDownLatch(254)
        val pool = Executors.newFixedThreadPool(48)
        for (i in 1..254) pool.execute {
            try {
                val url = "http://$prefix$i:$PORT"
                if (found.get() == null && isRelay(url)) found.compareAndSet(null, url)
            } finally {
                left.countDown()
            }
        }
        val until = System.currentTimeMillis() + 20000
        while (found.get() == null && left.count > 0 && System.currentTimeMillis() < until) Thread.sleep(50)
        pool.shutdownNow()
        return found.get()
    }

    private fun wifiAddress(): Inet4Address? {
        val all = try { NetworkInterface.getNetworkInterfaces()?.toList() ?: emptyList() } catch (e: Exception) { emptyList() }
        val up = all.filter { try { it.isUp && !it.isLoopback } catch (e: Exception) { false } }
        val addrs = { n: NetworkInterface -> n.inetAddresses.toList().filterIsInstance<Inet4Address>().filter { it.isSiteLocalAddress } }
        return up.filter { it.name.startsWith("wlan") }.flatMap(addrs).firstOrNull() ?: up.flatMap(addrs).firstOrNull()
    }

    private fun isRelay(base: String): Boolean = try {
        val c = URL("$base/health").openConnection() as HttpURLConnection
        c.connectTimeout = 800
        c.readTimeout = 1500
        try { c.responseCode == 200 && (c.getHeaderField("Server") ?: "").startsWith("OverheadRelay") } finally { c.disconnect() }
    } catch (e: Exception) {
        false
    }

    /** What a page can ask of the app (Settings). */
    inner class Bridge(private val view: WebView) {
        @JavascriptInterface
        fun changeRelay() {
            main.post { askAddress(null) }
        }

        /** The page, signed in over the Wi-Fi, hands over the relay's https address: a one-time link for this phone there. */
        @JavascriptInterface
        fun usePublic(link: String) {
            val u = Uri.parse(link)
            val host = u.host ?: return
            if (u.scheme != "https" || host.isEmpty() || !u.path.orEmpty().startsWith("/join/")) return
            val base = "https://$host" + if (u.port > 0) ":${u.port}" else ""
            main.post {
                if (relay == base || view !== web) return@post
                prefs.edit().putString(PUBLIC, base).apply()
                relay = base
                failed = false
                webReady = false
                handover = 1
                web.visibility = View.INVISIBLE
                showNote("Switching to the secure address …")
                web.loadUrl(link)
            }
        }

        /** 1.70: this phone's Firebase token if there is one already ("" otherwise). */
        @JavascriptInterface
        fun pushToken(): String = prefs.getString(PushService.TOKEN, null) ?: ""

        /** 1.70: turn notifications on: the permission, then the token, answered through window.fallblattPush. */
        @JavascriptInterface
        fun pushEnable() {
            main.post {
                if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != android.content.pm.PackageManager.PERMISSION_GRANTED)
                    requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQ_PUSH)
                else pushFetch()
            }
        }

        /** 1.71.1: Settings → Check for app updates. */
        @JavascriptInterface
        fun checkUpdate() {
            main.post { updater.check(asked = true) }
        }

        @JavascriptInterface
        fun locate() {
            main.post {
                locateFrom = view
                if (hasLocationPermission()) locateNow()
                else requestPermissions(arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION), REQ_LOCATION)
            }
        }

        /** A plane card's Share (1.53): the picture (base64 PNG) to the share sheet, through [ShareProvider]. */
        @JavascriptInterface
        fun shareImage(b64: String, name: String) {
            val bytes = try { android.util.Base64.decode(b64, android.util.Base64.DEFAULT) } catch (e: Exception) { return }
            if (bytes.isEmpty() || bytes.size > 15_000_000) return
            val safe = name.replace(Regex("[^A-Za-z0-9._-]"), "").removeSuffix(".png").ifEmpty { "fallblatt" } + ".png"
            val dir = java.io.File(cacheDir, "share")
            dir.mkdirs()
            dir.listFiles()?.forEach { it.delete() }
            java.io.File(dir, safe).writeBytes(bytes)
            val uri = Uri.parse("content://$packageName.share/$safe")
            main.post {
                val send = Intent(Intent.ACTION_SEND).setType("image/png").putExtra(Intent.EXTRA_STREAM, uri)
                    .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                send.clipData = android.content.ClipData.newRawUri("", uri)
                try { startActivity(Intent.createChooser(send, null)) } catch (e: Exception) { }
            }
        }
    }

    private fun hasLocationPermission() =
        checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
            checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, results: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, results)
        if (requestCode == REQ_CAMERA) {
            val r = camAsk; camAsk = null
            if (results.firstOrNull() == android.content.pm.PackageManager.PERMISSION_GRANTED) r?.grant(arrayOf(android.webkit.PermissionRequest.RESOURCE_VIDEO_CAPTURE)) else r?.deny()
            return
        }
        if (requestCode == REQ_PUSH) {
            if (results.firstOrNull() == android.content.pm.PackageManager.PERMISSION_GRANTED) pushFetch()
            else web.evaluateJavascript("window.fallblattPush && fallblattPush('', 'Notifications are turned off for Fallblatt in the phone\\'s settings.')", null)
            return
        }
        if (requestCode != REQ_LOCATION) return
        if (hasLocationPermission()) locateNow() else answerHere(null, "Location access was turned down. Allow it in the phone's settings for the Overhead app.")
    }

    /** A fresh position: a recent last-known one if there is one, otherwise the next fix (network first, then GPS). */
    @Suppress("MissingPermission")
    private fun locateNow() {
        val lm = getSystemService(LocationManager::class.java)
        val providers = listOf(LocationManager.NETWORK_PROVIDER, LocationManager.GPS_PROVIDER).filter {
            try { lm.isProviderEnabled(it) } catch (e: Exception) { false }
        }
        if (providers.isEmpty()) return answerHere(null, "Location is turned off on this phone. Turn it on and try again.")
        val recent = providers.mapNotNull { try { lm.getLastKnownLocation(it) } catch (e: SecurityException) { null } }
            .filter { System.currentTimeMillis() - it.time < 2 * 60_000 }
            .minByOrNull { it.accuracy }
        if (recent != null) return answerHere(recent, null)
        var done = false
        val cancel = CancellationSignal()
        val settle = { loc: Location?, err: String? ->
            if (!done) { done = true; cancel.cancel(); answerHere(loc, err) }
        }
        main.postDelayed({ settle(null, "The phone couldn't find its position in time. Try again, perhaps near a window.") }, 25_000)
        val provider = providers.first()
        try {
            if (Build.VERSION.SDK_INT >= 30) {
                lm.getCurrentLocation(provider, cancel, mainExecutor) { loc ->
                    if (loc != null) settle(loc, null)
                    else if (providers.size > 1) lm.getCurrentLocation(providers[1], cancel, mainExecutor) { l2 -> settle(l2, if (l2 == null) "The phone couldn't find its position." else null) }
                    else settle(null, "The phone couldn't find its position.")
                }
            } else {
                @Suppress("DEPRECATION")
                lm.requestSingleUpdate(provider, { loc -> settle(loc, null) }, Looper.getMainLooper())
            }
        } catch (e: Exception) {
            settle(null, "The phone couldn't find its position.")
        }
    }

    private fun answerHere(loc: Location?, err: String?) {
        val js = if (loc != null) "window.__overheadHere && window.__overheadHere(${loc.latitude}, ${loc.longitude}, ${loc.accuracy}, null)"
                 else "window.__overheadHere && window.__overheadHere(null, null, null, ${JSONObject.quote(err ?: "The location isn't available.")})"
        (locateFrom ?: web).evaluateJavascript(js, null)
    }

    override fun onResume() {
        super.onResume()
        web.onResume()                              // paused in onPause: without this the page stayed frozen and black
        applyOrientation()
        updater.resume()                            // back from allowing installs in the phone's settings
        updater.check()
    }

    override fun onPause() {
        web.onPause()
        super.onPause()
    }

    override fun onDestroy() {
        dialog?.dismiss()
        updater.close()
        web.destroy()
        super.onDestroy()
    }

    companion object {
        const val KEY = "relay"
        const val PUBLIC = "public"
        const val LIVE = "live"                  // the address the page last loaded from (the widgets try it first)
        const val REQ_LOCATION = 7
        const val REQ_PUSH = 8
        const val REQ_CAMERA = 9
        const val OPEN_URL = "openUrl"
        const val PORT = 8080
        val BG = 0xFF0B0B0C.toInt()
        val INK = 0xFFE8E2D0.toInt()
    }
}
