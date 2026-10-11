package io.github.belstria.overhead

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.WindowInsets
import android.webkit.JavascriptInterface
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

/**
 * The Overhead app: the relay's phone page (/app/) full screen. Everything on the page comes from the relay on the
 * home computer, so the app is always the current version; this activity only finds the relay and shows the page.
 *
 * On first start it looks for the relay on the Wi-Fi (every address of the phone's /24 network, port 8080, asking
 * /health and checking the relay's Server header). If it can't find one, or the saved relay doesn't answer, it asks
 * for the address. The page's Settings → About → Change relay calls [Bridge.changeRelay].
 */
class MainActivity : Activity() {
    private lateinit var web: WebView
    private lateinit var note: TextView
    private val main = Handler(Looper.getMainLooper())
    private val prefs by lazy { getSharedPreferences("overhead", MODE_PRIVATE) }
    private var relay: String? = null
    private var failed = false
    private var searching = false
    private var dialog: AlertDialog? = null

    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        val root = FrameLayout(this)
        root.setBackgroundColor(BG)
        web = WebView(this)
        web.setBackgroundColor(BG)
        web.visibility = View.INVISIBLE
        note = TextView(this)
        note.setTextColor(INK)
        note.textSize = 17f
        note.gravity = Gravity.CENTER
        note.setPadding(64, 64, 64, 64)
        root.addView(web, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))
        root.addView(note, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))
        setContentView(root)
        // Keep the page clear of the status bar, the navigation bar and a camera cutout (Android 15 draws edge to edge).
        root.setOnApplyWindowInsetsListener { v, insets ->
            if (Build.VERSION.SDK_INT >= 30) {
                val b = insets.getInsets(WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout())
                v.setPadding(b.left, b.top, b.right, b.bottom)
            } else {
                @Suppress("DEPRECATION")
                v.setPadding(insets.systemWindowInsetLeft, insets.systemWindowInsetTop, insets.systemWindowInsetRight, insets.systemWindowInsetBottom)
            }
            insets
        }
        setUpWeb()
        val saved = prefs.getString(KEY, null)
        if (saved != null) open(saved) else search()
    }

    private fun setUpWeb() {
        val s = web.settings
        s.javaScriptEnabled = true
        s.domStorageEnabled = true                  // the page keeps its settings in localStorage
        s.mediaPlaybackRequiresUserGesture = false  // flap sound and chimes
        val version = try { packageManager.getPackageInfo(packageName, 0).versionName } catch (e: Exception) { "?" }
        s.userAgentString = "${s.userAgentString} OverheadAndroid/$version"   // the relay lists the phone as the app
        web.addJavascriptInterface(Bridge(), "OverheadAndroid")
        web.webChromeClient = WebChromeClient()
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val url = request.url
                if (relay != null && url.host == Uri.parse(relay).host) return false
                // Links away from the relay (photo credits, the big board's sources) open in the browser.
                try { startActivity(Intent(Intent.ACTION_VIEW, url)) } catch (e: Exception) { }
                return true
            }

            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                if (!request.isForMainFrame) return
                failed = true
                web.visibility = View.INVISIBLE
                showNote("Can't reach the relay at $relay.")
                askAddress("Can't reach the relay at $relay. Is the computer on, the relay running, and this phone on the home Wi-Fi?")
            }

            override fun onPageFinished(view: WebView, url: String) {
                if (failed || url.startsWith("about:")) return
                web.visibility = View.VISIBLE
                note.visibility = View.GONE
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
        showNote("Connecting to $base …")
        web.loadUrl("$base/app/")
    }

    private fun use(base: String) {
        prefs.edit().putString(KEY, base).apply()
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
        val loaded = !failed && relay != null && web.visibility == View.VISIBLE
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

    /** What the page can ask of the app (Settings → About). */
    inner class Bridge {
        @JavascriptInterface
        fun changeRelay() {
            main.post { askAddress(null) }
        }
    }

    override fun onResume() {
        super.onResume()
        web.onResume()
    }

    override fun onPause() {
        web.onPause()
        super.onPause()
    }

    override fun onDestroy() {
        dialog?.dismiss()
        web.destroy()
        super.onDestroy()
    }

    companion object {
        const val KEY = "relay"
        const val PORT = 8080
        val BG = 0xFF0B0B0C.toInt()
        val INK = 0xFFE8E2D0.toInt()
    }
}
