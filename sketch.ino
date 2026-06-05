#include <Arduino.h>
#include <DHT.h>

#define DHTPIN 2        // <-- Change this to the physical digital pin your DHT signal wire is plugged into
#define DHTTYPE DHT11   // <-- Change to DHT22 if you are using the white DHT22 sensor instead of the blue DHT11

DHT dht(DHTPIN, DHTTYPE);
int servoAngle = 90;

// This function automatically handles Python's request for temperature
String getTemperature(String args) {
  float t = dht.readTemperature();
  
  // Check if the sensor read failed (returns NaN)
  if (isnan(t)) {
    return "ERROR";
  }
  return String(t, 1); // Returns temperature formatted to 1 decimal place (e.g., "24.3")
}

// This function automatically handles Python's request for humidity
String getHumidity(String args) {
  float h = dht.readHumidity();
  
  if (isnan(h)) {
    return "ERROR";
  }
  return String(h, 1); // Returns humidity formatted to 1 decimal place (e.g., "45.2")
}

String setAngle(String args) {
  if (args.length() > 0) {
    int newAngle = args.toInt();
    if (newAngle >= 0 && newAngle <= 180) {
      servoAngle = newAngle;
      // cameraServo.write(servoAngle); 
    }
  }
  return String(servoAngle);
}

void setup() {
  Bridge.begin();
  dht.begin(); // <-- Start the physical DHT sensor hardware layer
  
  while (!Bridge) {
    delay(10);
  }
  delay(1500); 

  // Register the endpoints so the Python background thread can call them
  Bridge.provide("temperature", getTemperature);
  Bridge.provide("humidity", getHumidity);
  Bridge.provide("set_angle", setAngle);
}

void loop() {
  // Keep empty so the background bridge has total control over timing
  delay(100); 
}
