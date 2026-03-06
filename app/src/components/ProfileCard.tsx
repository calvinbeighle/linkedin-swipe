import React from "react";
import {
  View,
  Text,
  Image,
  StyleSheet,
  TouchableOpacity,
  Linking,
  Dimensions,
} from "react-native";
import type { Profile } from "../types/profile";

const { width } = Dimensions.get("window");
const CARD_WIDTH = width - 40;

interface Props {
  profile: Profile;
}

export default function ProfileCard({ profile }: Props) {
  return (
    <View style={styles.card}>
      <Image
        source={{
          uri:
            profile.photo_url ||
            "https://ui-avatars.com/api/?name=" +
              encodeURIComponent(profile.name) +
              "&size=400&background=e8e8e8&color=333",
        }}
        style={styles.photo}
      />
      <View style={styles.info}>
        <Text style={styles.name}>{profile.name}</Text>
        {profile.headline ? (
          <Text style={styles.headline} numberOfLines={2}>
            {profile.headline}
          </Text>
        ) : null}
        {profile.company ? (
          <Text style={styles.company}>{profile.company}</Text>
        ) : null}
        {profile.location ? (
          <Text style={styles.location}>{profile.location}</Text>
        ) : null}
        <TouchableOpacity
          style={styles.linkedinBtn}
          onPress={() => Linking.openURL(profile.linkedin_url)}
        >
          <Text style={styles.linkedinText}>View on LinkedIn</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    width: CARD_WIDTH,
    height: 520,
    borderRadius: 3,
    backgroundColor: "#ffffff",
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 3,
    overflow: "hidden",
  },
  photo: {
    width: "100%",
    height: 300,
    backgroundColor: "rgba(0,0,0,0.03)",
  },
  info: {
    padding: 20,
    flex: 1,
  },
  name: {
    fontSize: 24,
    fontWeight: "700",
    color: "rgba(0,0,0,0.85)",
    letterSpacing: 0.2,
  },
  headline: {
    fontSize: 15,
    color: "rgba(0,0,0,0.7)",
    marginTop: 6,
    lineHeight: 20,
  },
  company: {
    fontSize: 14,
    color: "rgba(0,0,0,0.6)",
    marginTop: 4,
    fontStyle: "italic",
  },
  location: {
    fontSize: 12,
    color: "rgba(0,0,0,0.4)",
    marginTop: 4,
  },
  linkedinBtn: {
    marginTop: "auto",
    paddingVertical: 10,
    paddingHorizontal: 18,
    backgroundColor: "rgba(0,0,0,0.85)",
    borderRadius: 2,
    alignSelf: "flex-start",
  },
  linkedinText: {
    color: "rgba(255,255,255,0.9)",
    fontSize: 13,
    fontWeight: "600",
  },
});
