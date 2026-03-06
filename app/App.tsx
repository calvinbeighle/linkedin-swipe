import React from "react";
import { StatusBar } from "expo-status-bar";
import { NavigationContainer } from "@react-navigation/native";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { Text } from "react-native";
import SwipeScreen from "./src/screens/SwipeScreen";
import LikedScreen from "./src/screens/LikedScreen";

const Tab = createBottomTabNavigator();

export default function App() {
  return (
    <NavigationContainer>
      <StatusBar style="dark" />
      <Tab.Navigator
        screenOptions={{
          headerShown: false,
          tabBarActiveTintColor: "rgba(0,0,0,0.85)",
          tabBarInactiveTintColor: "rgba(0,0,0,0.3)",
          tabBarStyle: {
            backgroundColor: "#ffffff",
            borderTopColor: "rgba(0,0,0,0.1)",
          },
          tabBarLabelStyle: {
            fontSize: 11,
            fontWeight: "600",
            letterSpacing: 0.5,
          },
        }}
      >
        <Tab.Screen
          name="Swipe"
          component={SwipeScreen}
          options={{
            tabBarIcon: ({ color }) => (
              <Text style={{ fontSize: 22, color }}>&#9829;</Text>
            ),
          }}
        />
        <Tab.Screen
          name="Liked"
          component={LikedScreen}
          options={{
            tabBarIcon: ({ color }) => (
              <Text style={{ fontSize: 22, color }}>&#9733;</Text>
            ),
          }}
        />
      </Tab.Navigator>
    </NavigationContainer>
  );
}
