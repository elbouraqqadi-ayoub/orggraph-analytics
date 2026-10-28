"""Small native desktop viewer; no browser, external asset or extra dependency."""
import json
import queue
import threading
from pathlib import Path

from .core import analytics
from .pipeline import answer
from .services import read_neo4j


def launch(data: Path, backend="local"):
    import tkinter as tk
    from tkinter import ttk, messagebox

    root = tk.Tk()
    root.title("Entreprises et organisations — Knowledge Graph")
    root.geometry("1050x720")
    root.minsize(800, 560)
    root.configure(bg="#f1f5f9")
    frame = ttk.Frame(root, padding=20)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Entreprises et organisations", font=("Segoe UI", 20, "bold")).pack(anchor="w")
    status = tk.StringVar(value="Chargement du graphe…")
    ttk.Label(frame, textvariable=status).pack(anchor="w", pady=(4, 14))
    notebook = ttk.Notebook(frame)
    notebook.pack(fill="both", expand=True)
    entities_tab, facts_tab, ask_tab = [ttk.Frame(notebook, padding=12) for _ in range(3)]
    for tab, title in [(entities_tab, "Entités"), (facts_tab, "Relations et preuves"), (ask_tab, "Questions")]:
        notebook.add(tab, text=title)

    def table(parent, columns):
        widget = ttk.Treeview(parent, columns=columns, show="headings")
        for col in columns:
            widget.heading(col, text=col)
            widget.column(col, width=180, stretch=True)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=widget.yview)
        widget.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        widget.pack(fill="both", expand=True)
        return widget

    entity_table = table(entities_tab, ("Nom", "Type", "Degré"))
    fact_table = table(facts_tab, ("Source", "Relation", "Cible", "Preuves"))
    proof = tk.Text(facts_tab, height=7, wrap="word", state="disabled")
    proof.pack(fill="x", pady=(10, 0))
    ttk.Label(ask_tab, text="Question avec le nom complet d'une entité :").pack(anchor="w")
    question = ttk.Entry(ask_tab)
    question.insert(0, "Quels liens autour de Atlas Industries ?")
    question.pack(fill="x", pady=8)
    use_llm = tk.BooleanVar(value=False)
    ttk.Checkbutton(ask_tab, text="Utiliser le LLM configuré (envoi du contexte au fournisseur)", variable=use_llm).pack(anchor="w")
    result = tk.Text(ask_tab, wrap="word", font=("Segoe UI", 10), state="disabled")
    events = queue.Queue()
    state = {}

    def display(widget, value):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def ask():
        text, mode = question.get(), "llm" if use_llm.get() else "extractive"
        if not text.strip() or "graph" not in state:
            return
        button.configure(state="disabled")
        display(result, "Recherche en cours…")
        def work():
            try:
                events.put(("answer", answer(state["graph"], text, mode)))
            except Exception as exc:
                events.put(("error", str(exc)))
        threading.Thread(target=work, daemon=True).start()

    button = ttk.Button(ask_tab, text="Rechercher", command=ask)
    button.pack(anchor="w", pady=8)
    result.pack(fill="both", expand=True)

    def show_proof(_):
        selected = fact_table.selection()
        if selected:
            fact = state["facts"][selected[0]]
            docs = {d["id"]: d for d in state["graph"]["documents"]}
            display(proof, "\n\n".join(s["evidence"] + "\n" + docs[s["document_id"]]["source_uri"] for s in fact["supports"]))
    fact_table.bind("<<TreeviewSelect>>", show_proof)

    def load():
        try:
            graph = read_neo4j() if backend == "neo4j" else json.loads((data / "graph.json").read_text(encoding="utf-8"))
            events.put(("graph", graph))
        except Exception as exc:
            events.put(("error", str(exc)))

    def poll():
        try:
            while True:
                kind, value = events.get_nowait()
                if kind == "graph":
                    state["graph"] = value
                    stats = analytics(value)
                    status.set(f"{stats['documents']} documents • {stats['nodes']} entités • {stats['facts']} relations • backend {backend}")
                    for node in stats["degree_ranking"]:
                        entity_table.insert("", "end", values=(node["name"], node["kind"], node["degree"]))
                    names = {n["id"]: n["name"] for n in value["nodes"]}
                    state["facts"] = {f["id"]: f for f in value["facts"]}
                    for fact in value["facts"]:
                        fact_table.insert("", "end", iid=fact["id"], values=(names[fact["source"]], fact["type"], names[fact["target"]], len(fact["supports"])))
                elif kind == "answer":
                    display(result, value["answer"] + "\n\nSources :\n" + "\n".join(sorted({s["source_uri"] for row in value["context"] for s in row["sources"]})))
                    button.configure(state="normal")
                else:
                    status.set("Erreur — vérifier la configuration")
                    messagebox.showerror("Erreur", value)
                    button.configure(state="normal")
        except queue.Empty:
            pass
        root.after(100, poll)

    threading.Thread(target=load, daemon=True).start()
    root.after(100, poll)
    root.mainloop()
