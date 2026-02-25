import os
import re

HTML_HEADER = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Jeeves IRC Bot - The Butler's Ledger</title>
    <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;1,400&family=Lato:wght@300;400;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-dark: #0b0c10;
            --bg-panel: #1f2833;
            --bg-hover: #2c3a47;
            --gold-primary: #c5a059;
            --gold-light: #e6ce98;
            --gold-dark: #8c7335;
            --text-main: #e0e0e0;
            --text-muted: #8a8d91;
            --border-subtle: rgba(197, 160, 89, 0.2);
            --transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Lato', sans-serif;
            background-color: var(--bg-dark);
            background-image: radial-gradient(circle at top right, rgba(197, 160, 89, 0.05), transparent 400px);
            color: var(--text-main);
            line-height: 1.6;
            min-height: 100vh;
        }
        h1, h2, h3 { font-family: 'Playfair Display', serif; }
        .container { max-width: 1200px; margin: 0 auto; padding: 40px 20px; }
        header { text-align: center; margin-bottom: 60px; padding: 40px 0; border-bottom: 2px solid var(--gold-primary); position: relative; }
        header::after { content: '✨'; position: absolute; bottom: -14px; left: 50%; transform: translateX(-50%); font-size: 20px; color: var(--gold-primary); background: var(--bg-dark); padding: 0 10px; }
        h1 { color: var(--gold-light); font-size: 3.5rem; letter-spacing: 2px; text-transform: uppercase; text-shadow: 2px 2px 4px rgba(0,0,0,0.5); }
        .subtitle { color: var(--gold-dark); font-size: 1.2rem; font-style: italic; margin-top: 10px; }
        
        .controls { margin-bottom: 40px; text-align: center; }
        #searchInput { width: 100%; max-width: 600px; padding: 15px 25px; border-radius: 30px; background: rgba(31,40,51,0.7); border: 1px solid var(--border-subtle); color: white; font-size: 1.1rem; box-shadow: inset 0 2px 5px rgba(0,0,0,0.2); transition: var(--transition); }
        #searchInput:focus { border-color: var(--gold-primary); outline: none; box-shadow: 0 0 15px rgba(197, 160, 89, 0.2), inset 0 2px 5px rgba(0,0,0,0.2); }
        
        .masonry-grid { column-count: 2; column-gap: 30px; }
        @media (max-width: 900px) { .masonry-grid { column-count: 1; } }
        
        .module-card { background: var(--bg-panel); border: 1px solid var(--border-subtle); border-radius: 8px; margin-bottom: 30px; break-inside: avoid; overflow: hidden; transition: var(--transition); box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        .module-card:hover { transform: translateY(-4px); box-shadow: 0 12px 20px rgba(0,0,0,0.4); border-color: rgba(197, 160, 89, 0.4); }
        .module-header { padding: 20px 25px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; background: linear-gradient(to right, rgba(197, 160, 89, 0.1), transparent); border-bottom: 1px solid transparent; transition: var(--transition); }
        .module-card.expanded .module-header { border-bottom-color: var(--border-subtle); background: linear-gradient(to right, rgba(197, 160, 89, 0.15), rgba(197, 160, 89, 0.05)); }
        
        .module-title h2 { color: var(--gold-primary); font-size: 1.5rem; letter-spacing: 1px; }
        .file-badge { font-size: 0.8rem; color: var(--text-muted); font-family: monospace; }
        
        .expand-icon { color: var(--gold-dark); font-size: 1.2rem; transition: transform 0.3s ease; }
        .module-card.expanded .expand-icon { transform: rotate(180deg); color: var(--gold-primary); }
        
        .module-content { max-height: 0; overflow: hidden; transition: max-height 0.4s ease-in-out; background: rgba(11,12,16,0.5); }
        .module-card.expanded .module-content { max-height: 5000px; }
        .module-inner { padding: 15px 25px 25px; }
        
        .command-item { padding: 15px 0; border-bottom: 1px dashed rgba(255,255,255,0.05); display: flex; flex-direction: column; transition: var(--transition); }
        .command-item:last-child { border-bottom: none; }
        .command-item:hover { background: rgba(197, 160, 89, 0.05); padding-left: 10px; border-radius: 4px; }
        
        .command-syntax { color: #66fcf1; font-family: 'Courier New', monospace; font-size: 1.1rem; font-weight: bold; margin-bottom: 5px; }
        .admin-badge { background: rgba(255,107,107,0.1); color: #ff6b6b; padding: 2px 6px; border-radius: 4px; border: 1px solid rgba(255,107,107,0.3); font-size: 0.7rem; margin-left: 10px; vertical-align: middle; text-transform: uppercase; letter-spacing: 1px; }
        .command-desc { color: #c5c6c7; font-size: 0.95rem; line-height: 1.5; }
        
        #noResults { text-align: center; padding: 40px; color: var(--gold-dark); font-size: 1.2rem; font-style: italic; display: none; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>The Butler's Ledger</h1>
            <div class="subtitle">A Comprehensive Guide to Jeeves' Capabilities</div>
        </header>
        <div class="controls">
            <input type="text" id="searchInput" placeholder="Search the ledger for commands or modules...">
        </div>
        <div id="noResults">I regret to inform you, sir, that nothing matches your inquiry.</div>
        <div class="masonry-grid" id="modulesContainer">
"""

HTML_FOOTER = """
        </div>
    </div>
    <script>
        document.querySelectorAll('.module-header').forEach(h => {
            h.addEventListener('click', () => {
                h.closest('.module-card').classList.toggle('expanded');
            });
        });

        document.getElementById('searchInput').addEventListener('input', (e) => {
            const term = e.target.value.toLowerCase();
            let hasVisibleCards = false;
            
            document.querySelectorAll('.module-card').forEach(card => {
                let showCard = false;
                if (card.querySelector('h2').textContent.toLowerCase().includes(term)) showCard = true;
                if (card.querySelector('.file-badge').textContent.toLowerCase().includes(term)) showCard = true;
                
                let visibleCommands = 0;
                card.querySelectorAll('.command-item').forEach(cmd => {
                    if (cmd.textContent.toLowerCase().includes(term)) {
                        cmd.style.display = 'flex';
                        showCard = true;
                        visibleCommands++;
                    } else if (term) {
                        cmd.style.display = 'none';
                    } else {
                        cmd.style.display = 'flex';
                    }
                });
                
                card.style.display = showCard ? 'block' : 'none';
                if (term && showCard) {
                    hasVisibleCards = true;
                    if (visibleCommands > 0) card.classList.add('expanded');
                }
                else if (!term) card.classList.remove('expanded');
            });
            
            document.getElementById('noResults').style.display = (term && !hasVisibleCards) ? 'block' : 'none';
        });
    </script>
</body>
</html>
"""

def extract_commands(module_path):
    commands = []
    try:
        with open(module_path, 'r', encoding='utf-8') as f:
            content = f.read()

        import ast
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'register_command':
                    name = ''
                    desc = 'No description provided.'
                    admin = False
                    for kw in node.keywords:
                        if kw.arg == 'name' and isinstance(kw.value, ast.Constant):
                            name = kw.value.value
                        elif kw.arg == 'description' and isinstance(kw.value, ast.Constant):
                            desc = kw.value.value
                        elif kw.arg == 'admin_only' and isinstance(kw.value, ast.Constant):
                            admin = kw.value.value
                    if name:
                        commands.append({'name': name, 'desc': desc, 'admin': admin})
        except SyntaxError:
            pass # Skip unparseable files
    except Exception as e:
        print(f"Error parsing {module_path}: {e}")
        
    unique_cmds = {c['name']: c for c in commands}
    return list(unique_cmds.values())

def parse_and_write():
    modules_dir = 'modules'
    out_html = HTML_HEADER
    
    files = sorted([f for f in os.listdir(modules_dir) if f.endswith('.py')])
    
    for f in files:
        cmds = extract_commands(os.path.join(modules_dir, f))
        if not cmds: continue
        
        title = f.replace('.py', '').replace('_', ' ').title()
        
        out_html += f'''
            <div class="module-card">
                <div class="module-header">
                    <div class="module-title">
                        <h2>{title}</h2>
                        <div class="file-badge">{f}</div>
                    </div>
                    <div class="expand-icon">▼</div>
                </div>
                <div class="module-content">
                    <div class="module-inner">
        '''
        
        cmds.sort(key=lambda x: x['name'])
        
        for cmd in cmds:
            admin_badge = '<span class="admin-badge">Admin</span>' if cmd['admin'] else ''
            display_name = f"!{cmd['name']}"
            if " " in cmd['name']:
                parts = cmd['name'].split(" ", 1)
                display_name = f"!{parts[0]} <span style='color: #45a29e; font-style: italic;'>{parts[1]}</span>"
                
            out_html += f'''
                        <div class="command-item">
                            <div class="command-syntax">{display_name} {admin_badge}</div>
                            <div class="command-desc">{cmd['desc']}</div>
                        </div>
            '''
            
        out_html += '''
                    </div>
                </div>
            </div>
        '''
        
    out_html += HTML_FOOTER
    
    os.makedirs('docs', exist_ok=True)
    with open('docs/index.html', 'w', encoding='utf-8') as f:
        f.write(out_html)
    print("Generated docs/index.html successfully!")

if __name__ == '__main__':
    parse_and_write()
