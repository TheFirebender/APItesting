#!/usr/bin/env python3
"""
run.py — главная точка входа API Sentinel.

  python run.py gui          →  Запустить GUI на http://localhost:8765
  python run.py cli <cmd>    →  CLI-инструмент
  python run.py test         →  Запустить тесты
  python run.py cli --help   →  Справка по CLI
"""
import sys
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)


def run_gui():
    from gui.server import run
    run()


def run_cli():
    sys.argv = [sys.argv[0]] + sys.argv[2:]
    from cli.apisent import main
    main()


def run_tests():
    import unittest
    loader = unittest.TestLoader()
    suite  = loader.discover("tests", pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


HELP = """
  ╔════════════════════════════════════════════╗
  ║        API  S E N T I N E L                ║
  ║  HTTP-клиент для тестирования API          ║
  ╚════════════════════════════════════════════╝

  Использование:
    python run.py gui                     Запустить GUI
    python run.py test                    Запустить тесты
    python run.py cli send <url>          Отправить запрос
    python run.py cli run <коллекция>     Запустить коллекцию
    python run.py cli --help              Справка CLI

  Примеры:
    python run.py gui
    python run.py cli send https://jsonplaceholder.typicode.com/posts/1
    python run.py cli run "JSONPlaceholder Demo" --output-format junit -o report.xml
    python run.py cli env new production --var BASE_URL=https://api.example.com
    python run.py test
"""

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""

    if cmd == "gui":
        run_gui()
    elif cmd == "cli":
        run_cli()
    elif cmd == "test":
        run_tests()
    else:
        print(HELP)
        if cmd and cmd not in ("-h", "--help", "help"):
            print(f"  Неизвестная команда: {cmd}\n")
            sys.exit(1)
