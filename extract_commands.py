import os, re, json

data = {}
for root, _, files in os.walk('modules'):
    for f in files:
        if f.endswith('.py'):
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()
            
            # Find all register_command calls
            # extracting name, admin_only, and description
            pattern = r'register_command\([^,]+,\s*[^,]+,\s*name=[\'"]([^\'"]+)[\'"](?:,\s*admin_only=(True|False))?(?:,\s*description=[\'"]([^\'"]+)[\'"])?'
            matches = re.findall(pattern, content)
            if matches:
                data[f] = matches

with open('commands_output.json', 'w') as out:
    json.dump(data, out, indent=2)
