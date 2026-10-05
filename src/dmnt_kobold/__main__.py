import sys

if __name__ == "__main__":
    if "--katalog" in sys.argv:             # Katalog als Markdown (Grundlage der Autoren-Doku)
        from dmnt_kobold.katalog import als_markdown

        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        sys.stdout.write(als_markdown())
        raise SystemExit(0)

    from dmnt_kobold.app import main

    raise SystemExit(main())
