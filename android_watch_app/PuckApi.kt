package com.example.puckremote.presentation

import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.Body
import retrofit2.http.POST

// 1. data class: This matches the JSON you send to the Pi
// e.g. { "button": "1 ON" }
data class ControlRequest(
    val button: String
)

// 2. data class: This matches the JSON valid response from the Pi (optional, but good practice)
data class ControlResponse(
    val status: String,
    val message: String
)

// 3. Interface: Defines the API endpoints
interface PuckApi {
    @POST("/api/control")
    suspend fun triggerButton(@Body request: ControlRequest): ControlResponse
}

// 4. Singleton: The "Object" to access the API anywhere
object RetrofitClient {
    // ⚠️ CHANGE THIS TO YOUR RASPBERRY PI'S IP ADDRESS!
    private const val BASE_URL = "http://192.168.1.100:5000/" 

    val api: PuckApi by lazy {
        Retrofit.Builder()
            .baseUrl(BASE_URL)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(PuckApi::class.java)
    }
}
