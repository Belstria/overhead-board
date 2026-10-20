package io.github.belstria.overhead

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage

/**
 * The relay's notifications in the Android app (1.70), through Firebase Cloud Messaging: the WebView has no Web Push.
 * The relay sends data messages shaped like its Web Push ones (title, body, tag, kind, url, update), and they are shown
 * as the service worker shows them: one at a time under one tag, a countdown's update (`update`) quietly in place,
 * "Look up now" ringing again. A tap opens the app at the message's page.
 */
class PushService : FirebaseMessagingService() {
    override fun onNewToken(token: String) {
        getSharedPreferences("overhead", Context.MODE_PRIVATE).edit().putString(TOKEN, token).apply()
    }

    override fun onMessageReceived(msg: RemoteMessage) {
        val d = msg.data
        show(this, d["title"] ?: "Fallblatt", d["body"] ?: "", d["url"] ?: "/app/", d["update"] == "1", d["kind"] ?: "")
    }

    companion object {
        const val TOKEN = "fcmToken"
        private const val CHANNEL = "alerts"
        private const val ID = 7

        fun channel(context: Context) {
            val nm = context.getSystemService(NotificationManager::class.java)
            if (nm.getNotificationChannel(CHANNEL) == null) nm.createNotificationChannel(
                NotificationChannel(CHANNEL, "Planes worth a look", NotificationManager.IMPORTANCE_HIGH).apply {
                    description = "Special planes, favourites, the countdown, the evening summary"
                })
        }

        fun show(context: Context, title: String, body: String, url: String, quiet: Boolean, kind: String) {
            channel(context)
            val open = PendingIntent.getActivity(context, 0,
                Intent(context, MainActivity::class.java).putExtra(MainActivity.OPEN_URL, url).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
            val n = Notification.Builder(context, CHANNEL)
                .setSmallIcon(R.drawable.ic_plane)
                .setContentTitle(title)
                .setContentText(body.lineSequence().firstOrNull() ?: "")
                .setStyle(Notification.BigTextStyle().bigText(body))
                .setColor(0xFFF0B429.toInt())
                .setContentIntent(open)
                .setAutoCancel(true)
                .setOnlyAlertOnce(quiet)                      // an update replaces the alert without ringing again
                .setCategory(if (kind == "emergency") Notification.CATEGORY_ALARM else Notification.CATEGORY_RECOMMENDATION)
                .build()
            val nm = context.getSystemService(NotificationManager::class.java)
            if (!quiet) nm.cancel(ID)                          // "Look up now" and a new alert ring
            nm.notify(ID, n)
        }
    }
}
