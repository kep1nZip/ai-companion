from ai.companion import Companion
from developer.developer import DeveloperService

# Companion bisa dibuat tanpa Vision/GUI sama sekali — semuanya opsional
companion = Companion()

# Kirim 1 pesan dulu biar ada data Behavior/Memory buat dilihat
reply = companion.chat("Halo Arona, apa kabar?")
print(f"Arona: {reply}\n")

# avatar_manager/voice_manager sengaja None -> DeveloperService tetap aman,
# avatar snapshot-nya bakal nunjukin connection_state=None (karena GUI nggak jalan)
developer_service = DeveloperService(companion=companion)

print("=" * 50)
print(developer_service.export_markdown())
print("=" * 50)

snapshot = developer_service.get_snapshot()
print(f"\nBehavior emotion: {snapshot.behavior.emotion if snapshot.behavior else 'N/A'}")
print(f"Health: {snapshot.health}")