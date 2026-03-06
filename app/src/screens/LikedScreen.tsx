import React, { useEffect, useState } from "react";
import {
  View,
  Text,
  FlatList,
  StyleSheet,
  TouchableOpacity,
  Linking,
  Image,
  RefreshControl,
} from "react-native";
import { getLikedProfiles } from "../api/client";
import type { Profile } from "../types/profile";

export default function LikedScreen() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    try {
      const data = await getLikedProfiles();
      setProfiles(data);
    } catch (err) {
      console.error("Failed to load liked profiles:", err);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const renderItem = ({ item }: { item: Profile }) => (
    <TouchableOpacity
      style={styles.row}
      onPress={() => Linking.openURL(item.linkedin_url)}
      activeOpacity={0.7}
    >
      <Image
        source={{
          uri:
            item.photo_url ||
            "https://ui-avatars.com/api/?name=" +
              encodeURIComponent(item.name) +
              "&size=100&background=e8e8e8&color=333",
        }}
        style={styles.avatar}
      />
      <View style={styles.rowInfo}>
        <Text style={styles.rowName}>{item.name}</Text>
        {item.headline ? (
          <Text style={styles.rowHeadline} numberOfLines={1}>
            {item.headline}
          </Text>
        ) : null}
        {item.company ? (
          <Text style={styles.rowCompany}>{item.company}</Text>
        ) : null}
      </View>
    </TouchableOpacity>
  );

  return (
    <View style={styles.container}>
      <Text style={styles.header}>Liked Profiles</Text>
      <Text style={styles.count}>{profiles.length} connections queued</Text>
      <FlatList
        data={profiles}
        renderItem={renderItem}
        keyExtractor={(item) => item.id.toString()}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
        }
        ListEmptyComponent={
          <Text style={styles.empty}>
            No liked profiles yet. Swipe right to add people here.
          </Text>
        }
        contentContainerStyle={
          profiles.length === 0 ? styles.emptyContainer : undefined
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#ffffff",
    paddingTop: 60,
  },
  header: {
    fontSize: 20,
    fontWeight: "700",
    color: "rgba(0,0,0,0.85)",
    paddingHorizontal: 20,
    letterSpacing: 0.5,
  },
  count: {
    fontSize: 12,
    color: "rgba(0,0,0,0.4)",
    paddingHorizontal: 20,
    marginTop: 4,
    marginBottom: 12,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 14,
    paddingHorizontal: 20,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "rgba(0,0,0,0.1)",
  },
  avatar: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: "rgba(0,0,0,0.03)",
  },
  rowInfo: {
    marginLeft: 14,
    flex: 1,
  },
  rowName: {
    fontSize: 16,
    fontWeight: "600",
    color: "rgba(0,0,0,0.85)",
  },
  rowHeadline: {
    fontSize: 13,
    color: "rgba(0,0,0,0.6)",
    marginTop: 2,
  },
  rowCompany: {
    fontSize: 12,
    color: "rgba(0,0,0,0.4)",
    marginTop: 2,
    fontStyle: "italic",
  },
  empty: {
    fontSize: 14,
    color: "rgba(0,0,0,0.4)",
    textAlign: "center",
  },
  emptyContainer: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    padding: 40,
  },
});
