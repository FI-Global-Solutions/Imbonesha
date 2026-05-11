import { Tabs } from 'expo-router';
import { Text } from 'react-native';
import { colors } from '../../lib/theme';
import { useMyAssignments } from '../../lib/api/hooks';

function AssignmentsIcon({ focused }: { focused: boolean }) {
  return <Text style={{ fontSize: 20 }}>{focused ? '📋' : '📄'}</Text>;
}
function MapIcon({ focused }: { focused: boolean }) {
  return <Text style={{ fontSize: 20 }}>{focused ? '🗺️' : '🗺️'}</Text>;
}
function ProfileIcon({ focused }: { focused: boolean }) {
  return <Text style={{ fontSize: 20 }}>{focused ? '👤' : '👤'}</Text>;
}

function AssignmentsBadge() {
  const { data } = useMyAssignments();
  return data?.count && data.count > 0
    ? <Text style={{ color: '#fff', fontSize: 10, fontWeight: '700' }}>{data.count}</Text>
    : null;
}

export default function TabsLayout() {
  const { data } = useMyAssignments();
  const pendingCount = data?.count ?? 0;

  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.muted,
        tabBarStyle: { backgroundColor: colors.background, borderTopColor: colors.border },
        headerShown: false,
      }}
    >
      <Tabs.Screen
        name="assignments"
        options={{
          title: 'Assignments',
          tabBarIcon: ({ focused }) => <AssignmentsIcon focused={focused} />,
          tabBarBadge: pendingCount > 0 ? pendingCount : undefined,
        }}
      />
      <Tabs.Screen
        name="map"
        options={{
          title: 'Map',
          tabBarIcon: ({ focused }) => <MapIcon focused={focused} />,
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: 'Profile',
          tabBarIcon: ({ focused }) => <ProfileIcon focused={focused} />,
        }}
      />
    </Tabs>
  );
}
