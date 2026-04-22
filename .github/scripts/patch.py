import re

with open("compose.yml", "r") as f:
    content = f.read()

# Fix Coolify variable parsing
content = content.replace("${ADMIN_DOMAIN:-}", "${ADMIN_DOMAIN}")
content = content.replace("${ADMIN_DOMAIN:+https://${ADMIN_DOMAIN}}", "${ADMIN_DOMAIN}")

# Remove caddy service block entirely (Traefik replaces it)
content = re.sub(r"^  caddy:.*?(?=^  [a-z])", "", content, flags=re.MULTILINE | re.DOTALL)

# Remove caddy volumes
content = content.replace("  caddy_data:\n", "")
content = content.replace("  caddy_config:\n", "")

# Remove caddy from any depends_on
content = re.sub(r"^\s+caddy:\s*\n\s+condition:.*\n", "", content, flags=re.MULTILINE)
content = re.sub(r"^\s+- caddy\n", "", content, flags=re.MULTILINE)

with open("compose.yml", "w") as f:
    f.write(content)

print("Patched compose.yml successfully")
