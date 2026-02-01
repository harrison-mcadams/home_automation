package com.example.puckremote.presentation

import android.content.Context
import android.os.Build
import android.os.Bundle
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.wear.compose.material.*
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                PuckApp()
            }
        }
    }
}

@Composable
fun PuckApp() {
    val scope = rememberCoroutineScope()
    var statusText by remember { mutableStateOf("Ready") }
    val context = LocalContext.current

    // ScalingLazyColumn is the "standard" for Wear OS lists
    ScalingLazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .background(Color.Black),
        horizontalAlignment = Alignment.CenterHorizontally,
        contentPadding = PaddingValues(top = 20.dp, bottom = 20.dp)
    ) {
        item {
            Text(
                "Puck Remote", 
                style = MaterialTheme.typography.caption1, 
                color = Color.Cyan
            )
        }

        // Generate rows for Outlets 1 through 5
        items(5) { index ->
            val outletNum = index + 1
            Spacer(modifier = Modifier.height(12.dp))
            OutletRow(
                num = outletNum,
                onControl = { state ->
                    vibrate(context)
                    statusText = "Channel $outletNum $state..."
                    scope.launch {
                        sendSignal("$outletNum $state", 
                            onSuccess = { statusText = "Sent!" }, 
                            onError = { statusText = "Failed!" }
                        )
                    }
                }
            )
        }

        item {
            Spacer(modifier = Modifier.height(10.dp))
            Text(statusText, style = MaterialTheme.typography.body2, color = Color.Gray)
        }
    }
}

@Composable
fun OutletRow(num: Int, onControl: (String) -> Unit) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text("OUTLET $num", style = MaterialTheme.typography.display3)
        Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
            // ON Button
            CompactButton(
                onClick = { onControl("ON") },
                colors = ButtonDefaults.buttonColors(backgroundColor = Color(0xFF2E7D32)),
            ) { Text("ON") }
            
            // OFF Button
            CompactButton(
                onClick = { onControl("OFF") },
                colors = ButtonDefaults.buttonColors(backgroundColor = Color(0xFFC62828)),
            ) { Text("OFF") }
        }
    }
}

fun vibrate(context: Context) {
    val vibrator = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
        val vibratorManager = context.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as VibratorManager
        vibratorManager.defaultVibrator
    } else {
        @Suppress("DEPRECATION")
        context.getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
    }
    vibrator.vibrate(VibrationEffect.createOneShot(50, VibrationEffect.DEFAULT_AMPLITUDE))
}

suspend fun sendSignal(btnName: String, onSuccess: () -> Unit, onError: () -> Unit) {
    try {
        RetrofitClient.api.triggerButton(ControlRequest(btnName))
        onSuccess()
    } catch (e: Exception) {
        e.printStackTrace()
        onError()
    }
}
