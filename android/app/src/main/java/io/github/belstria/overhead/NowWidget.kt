package io.github.belstria.overhead

import android.app.AlarmManager
import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Shader
import android.graphics.Typeface
import android.net.Uri
import android.os.PowerManager
import android.os.SystemClock
import android.view.View
import android.webkit.CookieManager
import android.widget.RemoteViews
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * The plane overhead on the home screen (1.67), in two sizes: [NowWidgetCard] (4×2: the flight on split flaps, its
 * status, airline and type, route and where it is) and [NowWidgetLine] (4×1: one line). Both read the relay's /now with
 * the app's own sign-in (the WebView's cookie for the relay) and open the app when tapped. They refresh about once a
 * minute while the phone's screen is on (a non-waking alarm), and at least every half hour (Android's own update).
 */
abstract class NowWidget : AppWidgetProvider() {
    abstract val layout: Int
    abstract fun fill(context: Context, v: RemoteViews, plane: JSONObject?, today: Int, note: String?)

    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) {
        refresh(context, manager, ids)
        tick(context, true)
    }

    override fun onDisabled(context: Context) = tick(context, false)

    override fun onReceive(context: Context, intent: Intent) {
        super.onReceive(context, intent)
        if (intent.action != ACTION_TICK) return
        val power = context.getSystemService(Context.POWER_SERVICE) as PowerManager
        if (!power.isInteractive) return                       // nobody is looking: no data used
        val manager = AppWidgetManager.getInstance(context)
        val ids = manager.getAppWidgetIds(ComponentName(context, javaClass))
        if (ids.isNotEmpty()) refresh(context, manager, ids)
    }

    /** A minute's alarm that doesn't wake the phone, while widgets of this size are on the home screen. */
    private fun tick(context: Context, on: Boolean) {
        val alarms = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        val pi = PendingIntent.getBroadcast(context, javaClass.name.hashCode(), Intent(context, javaClass).setAction(ACTION_TICK),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        alarms.cancel(pi)
        if (on) alarms.setRepeating(AlarmManager.ELAPSED_REALTIME, SystemClock.elapsedRealtime() + 60_000, 60_000, pi)
    }

    private fun refresh(context: Context, manager: AppWidgetManager, ids: IntArray) {
        val pending = goAsync()
        Thread {
            try {
                val (j, note) = fetchNow(context)
                for (id in ids) {
                    val v = RemoteViews(context.packageName, layout)
                    fill(context, v, j?.optJSONObject("plane"), j?.optInt("today") ?: 0, note)
                    val open = PendingIntent.getActivity(context, 0, Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                        PendingIntent.FLAG_IMMUTABLE)
                    v.setOnClickPendingIntent(R.id.w_root, open)
                    manager.updateAppWidget(id, v)
                }
            } finally {
                pending.finish()
            }
        }.start()
    }

    /** The relay's /now, as the app's signed-in device: (answer, null) or (null, why not). 1.69: the address the app's
     *  page last loaded from first, then the https one, then the Wi-Fi one (away from home that one can't answer). */
    private fun fetchNow(context: Context): Pair<JSONObject?, String?> {
        val prefs = context.getSharedPreferences("overhead", Context.MODE_PRIVATE)
        val bases = listOfNotNull(prefs.getString(MainActivity.LIVE, null), prefs.getString(MainActivity.PUBLIC, null),
            prefs.getString(MainActivity.KEY, null)).distinct()
        if (bases.isEmpty()) return null to "Open the app once to set it up"
        var why = "No connection"
        for (base in bases) {
            try {
                val cookie = try { CookieManager.getInstance().getCookie(base) } catch (e: Exception) { null }
                val c = URL("$base/now").openConnection() as HttpURLConnection
                c.connectTimeout = 5000
                c.readTimeout = 8000
                c.instanceFollowRedirects = false
                if (cookie != null) c.setRequestProperty("Cookie", cookie)
                try {
                    when (c.responseCode) {
                        200 -> return JSONObject(c.inputStream.bufferedReader().readText()) to null
                        401, 403 -> why = "Open the app to sign in"
                        else -> why = "No answer from the board (${c.responseCode})"
                    }
                } finally { c.disconnect() }
            } catch (e: Exception) {
                why = "No connection · " + (Uri.parse(base).host ?: base)
            }
        }
        return null to why
    }

    companion object {
        const val ACTION_TICK = "io.github.belstria.overhead.WIDGET_TICK"
        val AMBER = 0xFFF0B429.toInt()
        val INK = 0xFFF3F0E8.toInt()
        val MUTED = 0xFF959AA3.toInt()

        /** The boards' status colours (REMARK_LOOK): the lamp behind the word. */
        fun statusColour(word: String): Int = when (word) {
            "OVERHEAD" -> 0xFF27A85E.toInt()
            "APPROACHING" -> 0xFFE0A11B.toInt()
            "LEAVING" -> 0xFFC0473F.toInt()
            else -> 0xFF2F5FA8.toInt()
        }

        fun place(p: JSONObject?): String = p?.let { listOf(it.optString("code"), it.optString("city")).filter { s -> s.isNotEmpty() && s != "null" }.joinToString(" ") } ?: ""

        fun where(p: JSONObject): String {
            val alt = if (p.isNull("altM")) "" else " · %,d m".format(p.optInt("altM"))
            return "%.1f km %s".format(p.optDouble("dist"), p.optString("dir")) + alt
        }

        /** The flight on split flaps: a dark module per letter, split across the middle, the letter in white. */
        fun flaps(text: String, cells: Int = 7, h: Int = 96): Bitmap {
            val w = (h * .72f).toInt()
            val gap = (h * .06f).toInt()
            val bmp = Bitmap.createBitmap(cells * (w + gap), h, Bitmap.Config.ARGB_8888)
            val g = Canvas(bmp)
            val face = Paint(Paint.ANTI_ALIAS_FLAG)
            val ink = Paint(Paint.ANTI_ALIAS_FLAG).apply {
                color = INK; textAlign = Paint.Align.CENTER; textSize = h * .66f
                typeface = Typeface.create("sans-serif-condensed", Typeface.BOLD)
            }
            val split = Paint().apply { color = 0xFF000000.toInt(); strokeWidth = h * .03f }
            val t = text.uppercase().take(cells).padEnd(cells)
            for (i in 0 until cells) {
                val x = i * (w + gap).toFloat()
                face.shader = LinearGradient(0f, 0f, 0f, h.toFloat(), intArrayOf(0xFF2B2C2F.toInt(), 0xFF1C1D1F.toInt(), 0xFF161719.toInt()),
                    floatArrayOf(0f, .5f, 1f), Shader.TileMode.CLAMP)
                g.drawRoundRect(RectF(x, 0f, x + w, h.toFloat()), h * .07f, h * .07f, face)
                val ch = t[i].toString()
                if (ch.isNotBlank()) g.drawText(ch, x + w / 2f, h / 2f - (ink.descent() + ink.ascent()) / 2f, ink)
                g.drawLine(x, h / 2f, x + w, h / 2f, split)
            }
            return bmp
        }

        /** The status word on its lamp, a small rounded pill. */
        fun pill(word: String, h: Int = 44): Bitmap {
            val p = Paint(Paint.ANTI_ALIAS_FLAG).apply {
                color = 0xFFFFFFFF.toInt(); textSize = h * .52f; typeface = Typeface.create("sans-serif-condensed", Typeface.BOLD)
                letterSpacing = .08f
            }
            val w = (p.measureText(word) + h * .7f).toInt().coerceAtLeast(h)
            val bmp = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
            val g = Canvas(bmp)
            g.drawRoundRect(RectF(0f, 0f, w.toFloat(), h.toFloat()), h * .2f, h * .2f, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = statusColour(word) })
            g.drawText(word, h * .35f, h / 2f - (p.descent() + p.ascent()) / 2f, p)
            return bmp
        }
    }
}

/** 4×2: the flap card (the mockup's A). */
class NowWidgetCard : NowWidget() {
    override val layout = R.layout.widget_card
    override fun fill(context: Context, v: RemoteViews, plane: JSONObject?, today: Int, note: String?) {
        v.setTextViewText(R.id.w_today, if (note == null) "Today $today" else "")
        if (plane == null) {
            v.setImageViewBitmap(R.id.w_flaps, flaps(""))
            v.setViewVisibility(R.id.w_status, View.GONE)
            v.setTextViewText(R.id.w_title, note ?: "No plane overhead right now")
            v.setTextViewText(R.id.w_sub, "")
            return
        }
        val word = plane.optString("status")
        v.setImageViewBitmap(R.id.w_flaps, flaps(plane.optString("flight")))
        v.setViewVisibility(R.id.w_status, View.VISIBLE)
        v.setImageViewBitmap(R.id.w_status, pill(word))
        v.setContentDescription(R.id.w_status, word)
        v.setTextViewText(R.id.w_title, listOf(plane.optString("airline"), plane.optString("type")).filter { it.isNotEmpty() }.joinToString(" · "))
        val route = if (plane.isNull("from") || plane.isNull("to")) "" else place(plane.optJSONObject("from")) + " → " + place(plane.optJSONObject("to")) + " · "
        v.setTextViewText(R.id.w_sub, route + where(plane))
    }
}

/** 4×1: one line (the mockup's B). */
class NowWidgetLine : NowWidget() {
    override val layout = R.layout.widget_line
    override fun fill(context: Context, v: RemoteViews, plane: JSONObject?, today: Int, note: String?) {
        if (plane == null) {
            v.setTextViewText(R.id.w_title, "")
            v.setTextViewText(R.id.w_sub, note ?: "No plane overhead right now · today $today")
            v.setInt(R.id.w_icon, "setColorFilter", MUTED)
            return
        }
        v.setTextViewText(R.id.w_title, plane.optString("flight"))
        val route = if (plane.isNull("from") || plane.isNull("to")) "" else
            plane.optJSONObject("from")?.optString("code") + "→" + plane.optJSONObject("to")?.optString("code") + " · "
        v.setTextViewText(R.id.w_sub, listOf(plane.optString("type"), route + "%.1f km %s".format(plane.optDouble("dist"), plane.optString("dir")))
            .filter { it.isNotBlank() }.joinToString(" · "))
        v.setInt(R.id.w_icon, "setColorFilter", statusColour(plane.optString("status")))
    }
}
