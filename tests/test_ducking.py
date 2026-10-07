#!/usr/bin/env python3
"""
Test: verificação manual de ducking de áudio via WirePlumber.
"""
import sys, os
import time

# Importa o script 'dictate' (que não tem extensão .py) de forma dinâmica
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from jrwhisper import audio

def test_ducking():
    print("=" * 60)
    print("TESTE DE DUCKING DE ÁUDIO (WirePlumber)")
    print("=" * 60)
    
    # 1. Lê o volume inicial
    vol, muted = audio.get_current_volume()
    if vol is None:
        print("FALHA: Não foi possível obter o volume atual do sistema!")
        sys.exit(1)
        
    print(f"Volume atual detectado: {vol:.2f} (Muted: {muted})")
    
    # 2. Aplica ducking (20% do volume)
    duck_vol = 0.20
    print(f"Reduzindo volume para: {duck_vol:.2f} (Aguarde 3 segundos)...")
    audio.set_volume(duck_vol)
    
    # Verifica se alterou
    new_vol, _ = audio.get_current_volume()
    print(f"Volume medido durante o ducking: {new_vol:.2f}")
    
    time.sleep(3.0)
    
    # 3. Restaura volume original
    print(f"Restaurando volume original para: {vol:.2f}...")
    audio.set_volume(vol)
    
    final_vol, _ = audio.get_current_volume()
    print(f"Volume final medido: {final_vol:.2f}")
    
    if abs(final_vol - vol) < 0.02:
        print("SUCESSO: O volume foi restaurado corretamente!")
    else:
        print("AVISO: O volume final é diferente do original!")
        
    print("=" * 60)

if __name__ == "__main__":
    test_ducking()
