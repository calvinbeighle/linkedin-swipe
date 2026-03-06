import React, { useCallback, useEffect, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ActivityIndicator,
  TouchableOpacity,
  Dimensions,
} from "react-native";
import { WebView } from "react-native-webview";
import { getPendingProfiles, recordSwipe } from "../api/client";
import type { Profile } from "../types/profile";

const { width } = Dimensions.get("window");

export default function SwipeScreen() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [pageLoading, setPageLoading] = useState(true);
  const [swiping, setSwiping] = useState(false);

  useEffect(() => {
    loadProfiles();
  }, []);

  const loadProfiles = async () => {
    try {
      setLoading(true);
      const data = await getPendingProfiles(50);
      setProfiles(data);
      setCurrentIndex(0);
    } catch (err) {
      console.error("Failed to load profiles:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleAction = useCallback(
    async (direction: "right" | "left") => {
      const profile = profiles[currentIndex];
      if (!profile || swiping) return;

      setSwiping(true);
      try {
        await recordSwipe(profile.id, direction);
        setCurrentIndex((prev) => prev + 1);
        setPageLoading(true);
      } catch (err) {
        console.error("Failed to record swipe:", err);
      } finally {
        setSwiping(false);
      }
    },
    [profiles, currentIndex, swiping],
  );

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="rgba(0,0,0,0.5)" />
        <Text style={styles.loadingText}>Loading profiles...</Text>
      </View>
    );
  }

  const currentProfile = profiles[currentIndex];

  if (!currentProfile) {
    return (
      <View style={styles.center}>
        <Text style={styles.emptyTitle}>All caught up</Text>
        <Text style={styles.emptySubtitle}>
          New profiles arrive each morning at 8 AM
        </Text>
        <TouchableOpacity style={styles.refreshBtn} onPress={loadProfiles}>
          <Text style={styles.refreshText}>Refresh</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>LinkedIn Swipe</Text>
        <Text style={styles.counter}>
          {currentIndex + 1} / {profiles.length}
        </Text>
      </View>

      {/* Name bar */}
      {currentProfile.name && currentProfile.name !== "Profile" && (
        <View style={styles.nameBar}>
          <Text style={styles.nameText}>{currentProfile.name}</Text>
        </View>
      )}

      {/* WebView showing the LinkedIn profile */}
      <View style={styles.webviewContainer}>
        {pageLoading && (
          <View style={styles.webviewOverlay}>
            <ActivityIndicator size="small" color="rgba(0,0,0,0.4)" />
          </View>
        )}
        <WebView
          source={{ uri: currentProfile.linkedin_url }}
          style={styles.webview}
          onLoadEnd={() => setPageLoading(false)}
          onLoadStart={() => setPageLoading(true)}
          sharedCookiesEnabled={true}
          thirdPartyCookiesEnabled={true}
          javaScriptEnabled={true}
          domStorageEnabled={true}
          startInLoadingState={false}
          userAgent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
        />
      </View>

      {/* Action buttons */}
      <View style={styles.actions}>
        <TouchableOpacity
          style={[styles.actionBtn, styles.skipBtn]}
          onPress={() => handleAction("left")}
          disabled={swiping}
          activeOpacity={0.7}
        >
          <Text style={styles.skipBtnText}>SKIP</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.actionBtn, styles.connectBtn]}
          onPress={() => handleAction("right")}
          disabled={swiping}
          activeOpacity={0.7}
        >
          <Text style={styles.connectBtnText}>CONNECT</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#e8e8e8",
  },
  center: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    backgroundColor: "#e8e8e8",
    padding: 40,
  },
  header: {
    paddingTop: 56,
    paddingBottom: 8,
    paddingHorizontal: 20,
    backgroundColor: "#ffffff",
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "rgba(0,0,0,0.1)",
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "baseline",
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: "700",
    color: "rgba(0,0,0,0.85)",
    letterSpacing: 0.3,
  },
  counter: {
    fontSize: 13,
    color: "rgba(0,0,0,0.4)",
  },
  nameBar: {
    backgroundColor: "#ffffff",
    paddingHorizontal: 20,
    paddingBottom: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "rgba(0,0,0,0.1)",
  },
  nameText: {
    fontSize: 15,
    fontWeight: "600",
    color: "rgba(0,0,0,0.7)",
  },
  webviewContainer: {
    flex: 1,
    position: "relative",
  },
  webview: {
    flex: 1,
  },
  webviewOverlay: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    zIndex: 10,
    paddingVertical: 8,
    backgroundColor: "rgba(255,255,255,0.9)",
    alignItems: "center",
  },
  actions: {
    flexDirection: "row",
    paddingHorizontal: 20,
    paddingVertical: 14,
    paddingBottom: 34,
    backgroundColor: "#ffffff",
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: "rgba(0,0,0,0.1)",
    gap: 16,
  },
  actionBtn: {
    flex: 1,
    paddingVertical: 14,
    borderRadius: 2,
    alignItems: "center",
  },
  skipBtn: {
    backgroundColor: "rgba(0,0,0,0.06)",
  },
  connectBtn: {
    backgroundColor: "rgba(0,0,0,0.85)",
  },
  skipBtnText: {
    fontSize: 15,
    fontWeight: "700",
    color: "rgba(0,0,0,0.5)",
    letterSpacing: 1,
  },
  connectBtnText: {
    fontSize: 15,
    fontWeight: "700",
    color: "rgba(255,255,255,0.95)",
    letterSpacing: 1,
  },
  loadingText: {
    marginTop: 12,
    fontSize: 14,
    color: "rgba(0,0,0,0.4)",
  },
  emptyTitle: {
    fontSize: 22,
    fontWeight: "700",
    color: "rgba(0,0,0,0.7)",
  },
  emptySubtitle: {
    fontSize: 14,
    color: "rgba(0,0,0,0.4)",
    marginTop: 8,
    textAlign: "center",
  },
  refreshBtn: {
    marginTop: 20,
    paddingVertical: 10,
    paddingHorizontal: 24,
    backgroundColor: "rgba(0,0,0,0.85)",
    borderRadius: 2,
  },
  refreshText: {
    color: "rgba(255,255,255,0.9)",
    fontSize: 14,
    fontWeight: "600",
  },
});
