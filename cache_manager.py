
import json
import os
import time


class CacheManager:
    def __init__(self, cache_dir):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.cache_metadata = self._load_metadata()
    
    def _load_metadata(self):
        metadata_file = os.path.join(self.cache_dir, "metadata.json")
        if os.path.exists(metadata_file):
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def _save_metadata(self):
        metadata_file = os.path.join(self.cache_dir, "metadata.json")
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(self.cache_metadata, f, ensure_ascii=False, indent=2)
    
    def get_cached_response(self, cache_key):
        arquivo_cache = os.path.join(self.cache_dir, f"{cache_key}.json")
        if os.path.exists(arquivo_cache):
            # Verificar validade do cache (ex: 24 horas)
            cache_age = time.time() - os.path.getmtime(arquivo_cache)
            if cache_age < 86400:  # 24 horas
                try:
                    with open(arquivo_cache, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except:
                    pass
        return None
    
    def save_response(self, cache_key, data):
        arquivo_cache = os.path.join(self.cache_dir, f"{cache_key}.json")
        with open(arquivo_cache, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        # Atualizar metadata
        self.cache_metadata[cache_key] = {
            'timestamp': time.time(),
            'size': len(str(data))
        }
        self._save_metadata()