#!/usr/bin/env python3
"""
Test: pipeline de formatação de texto importado do textproc.
"""
import sys, os
import re

# Importa o script 'dictate' (que não tem extensão .py) de forma dinâmica
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from jrwhisper import textproc

# Obtém a função de formatação diretamente do arquivo de produção
format_transcript = textproc.format_transcript


def run_tests():
    config = {
        "enable_formatting": True,
        "remove_fillers": True,
        "voice_commands": True,
        "word_overrides": {
            "m2a metais": "M2A Metais",
            "arcelormittal": "ArcelorMittal",
            "tesc": "TESC",
            "brutaldev": "brutaldev",
            "bl": "B/L",
            "booking": "Booking",
            "incoterms": "Incoterms"
        }
    }
    
    test_cases = [
        # (Texto de entrada, Texto esperado)
        (
            "olá mundo",
            "Olá mundo."
        ),
        (
            "olá mundo , tudo bem ? er humm vamos continuar",
            "Olá mundo, tudo bem? Vamos continuar."
        ),
        (
            "eu liguei para a m2a metais ontem vírgula mas não obtive retorno ponto final",
            "Eu liguei para a M2A Metais ontem, mas não obtive retorno."
        ),
        (
            "precisamos enviar o bl hoje à tarde nova linha por favor confirme o booking",
            "Precisamos enviar o B/L hoje à tarde\nPor favor confirme o Booking."
        ),
        (
            "este é um teste de dois pontos nova linha primeiro ponto e vírgula segundo novo parágrafo fim da linha",
            "Este é um teste de:\nPrimeiro; segundo\n\nFim da linha."
        ),
        (
            "comércio exterior e incoterms ahn são complexos",
            "Comércio exterior e Incoterms são complexos."
        ),
        (
            "você está pronto ponto de interrogação sim ponto de exclamação",
            "Você está pronto? Sim!"
        ),
        (
            "já tem ponto final no final.",
            "Já tem. No final."  # Com comandos ativos, "ponto final" vira "."
        ),
        (
            "texto com quebra de linha\n",
            "Texto com quebra de linha."
        ),
        # O Whisper pontua o próprio comando: nada de ",," ".." nem quebra de linha perdida
        ("Olá vírgula, tudo bem ponto final.", "Olá, tudo bem."),
        ("Primeira linha. Nova linha. segunda", "Primeira linha.\nSegunda."),
        ("Isso é ótimo. Ponto de exclamação!", "Isso é ótimo!"),
        ("o que é isso ponto de interrogação?", "O que é isso?"),
        ("olá, eh, tudo bem?", "Olá, tudo bem?"),
        ("Espere... já volto", "Espere... Já volto."),
    ]
    
    failed = False
    for junk in ("Acesse www.Incoterms.com.br para receber notificações de novos vídeos.",
                 "Legendas pela comunidade Amara.org", "Obrigado por assistir!",
                 "Acesse o link na descrição do vídeo para ver mais detalhes sobre os produtos.",
                 "Acesse o site www.incoterms.com.br e acesse o link na descrição do vídeo para receber "
                 "notificações de novos vídeos."):
        assert textproc.is_hallucination(junk), junk
    assert not textproc.is_hallucination("Preciso das notificações de novos vídeos do canal da empresa "
                                         "para o relatório de marketing de amanhã cedo, por favor, sem falta mesmo, porque o diretor "
                                         "pediu isso ontem.")
    assert not textproc.is_hallucination("Obrigado pela reunião de hoje.")
    print("Alucinações: PASSED")
    print("=" * 60)
    print("EXECUTANDO TESTES DO FORMATADOR DE TEXTO IMPORTADO DE DICTATE")
    print("=" * 60)
    
    for i, (input_text, expected_text) in enumerate(test_cases, 1):
        result = format_transcript(input_text, config)
        if result == expected_text:
            print(f"Test {i}: PASSED")
        else:
            print(f"Test {i}: FAILED")
            print(f"  Input:    {repr(input_text)}")
            print(f"  Expected: {repr(expected_text)}")
            print(f"  Result:   {repr(result)}")
            failed = True
            
    print("=" * 60)
    if failed:
        print("RESULTADO: ALGUNS TESTES FALHARAM!")
        sys.exit(1)
    else:
        print("RESULTADO: TODOS OS TESTES PASSARAM COM SUCESSO!")
        sys.exit(0)


if __name__ == "__main__":
    run_tests()
