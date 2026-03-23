import os
from supabase import create_client, Client

class SupabaseClient:
    def __init__(self):
        url = os.environ.get('SUPABASE_URL')
        key = os.environ.get('SUPABASE_KEY')
        if not url or not key:
            self.client = None
        else:
            # Add timeout to handle transient network issues or slow backend responses (Kong gateway)
            self.client: Client = create_client(url, key)
            # Modificando internamente o timeout no cliente httpx subjacente 
            # já que o create_client padrão usa timeouts baixos (5s)
            try:
                self.client.postgrest.session.timeout = 60
                self.client.storage.session.timeout = 60
            except:
                pass

    def get_client(self):
        return self.client

# Singleton adapter
db_adapter = SupabaseClient()
