"""N.A.N.I. (Neural Analytical Network Intelligence)
Entry point to launch the AI co-pilot console.
"""

from nani.interfaces.cli import NaniCLI

def main():
    cli = NaniCLI()
    cli.chat_loop()

if __name__ == "__main__":
    main()
