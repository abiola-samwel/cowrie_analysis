#!/usr/bin/env python3
import os
import subprocess
import time
import pandas as pd
from tabulate import tabulate
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

OUTPUT_DIR = "analysis_output"

def run_analyzer():
    """Run the analyzer script and show summary report"""
    print(Fore.CYAN + "\n[+] Running analyzer...\n")
    subprocess.call(["python3", "cowrie_analyzer.py"])

    # Show summary tables (Top 10 rows each)
    print(Fore.GREEN + "\n[+] Analyzer completed. Summary report:\n")
    show_tables_once()

    # Check graph files
    print(Fore.GREEN + "\n[+] Graphs generated:\n")
    graphs = ["top_ips.png", "top_creds.png", "timeline.png"]
    for g in graphs:
        path = os.path.join(OUTPUT_DIR, g)
        if os.path.exists(path):
            print("   " + Fore.GREEN + f"✔ {g}")
        else:
            print("   " + Fore.RED + f"✘ {g} (not found)")

def view_graphs():
    """List generated graphs and explain how to view them"""
    print(Fore.GREEN + "\n[+] Graphs are saved in analysis_output/")
    print("    - Local: open directly with an image viewer")
    print("    - Remote VM: download via scp or SFTP\n")

    graphs = ["top_ips.png", "top_creds.png", "timeline.png"]
    for g in graphs:
        path = os.path.join(OUTPUT_DIR, g)
        if os.path.exists(path):
            print("   " + Fore.GREEN + f"✔ {g}")
        else:
            print("   " + Fore.RED + f"✘ {g} (not found)")

def show_tables_once():
    """Display CSV results once"""
    files = {
        "Top IPs": "cowrie_attackers.csv",
        "Credentials": "cowrie_creds.csv",
        "Timeline": "cowrie_timeline.csv"
    }

    for title, fname in files.items():
        path = os.path.join(OUTPUT_DIR, fname)
        if not os.path.exists(path):
            print(Fore.RED + f"[!] {title}: {fname} missing (run analyzer first)\n")
            continue

        try:
            df = pd.read_csv(path)
            print(Fore.CYAN + f"\n--- {title} ---")
            print(tabulate(df.head(10), headers="keys", tablefmt="psql", showindex=False))
        except Exception as e:
            print(Fore.RED + f"[!] Error reading {fname}: {e}")

def view_tables():
    """Interactive refreshable view of tables"""
    refresh = input(Fore.CYAN + "Enter refresh time in seconds (Enter = one-shot): ").strip()
    if refresh.isdigit():
        refresh = int(refresh)
        try:
            while True:
                os.system("clear")
                show_tables_once()
                print(Fore.YELLOW + f"\n[Refreshing every {refresh}s] Press Ctrl+C to stop.")
                time.sleep(refresh)
        except KeyboardInterrupt:
            print(Fore.RED + "\n[!] Refresh stopped.")
    else:
        show_tables_once()

def main():
    while True:
        print(Fore.MAGENTA + "\n=== Live Cowrie Dashboard ===")
        print("1 → Run Analyzer (with summary)")
        print("2 → View Graphs")
        print("3 → View Tables (Top IPs, Creds, Timeline)")
        print("4 → Exit")

        choice = input(Fore.CYAN + "\nEnter choice: ").strip()

        if choice == "1":
            run_analyzer()
        elif choice == "2":
            view_graphs()
        elif choice == "3":
            view_tables()
        elif choice == "4":
            print(Fore.GREEN + "\nExiting dashboard. Goodbye!\n")
            break
        else:
            print(Fore.RED + "[!] Invalid choice, try again.")

if __name__ == "__main__":
    main()
