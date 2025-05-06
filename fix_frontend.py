import re

with open('CML-NetworkBuilder/Frontend.py', 'r') as f:
    content = f.read()

# Replace the problematic section (double else statements)
pattern = r'(                                else:\s+st\.info\("No devices available in the topology\.")\s+else:\s+st\.info\("No topology loaded\. Generate a topology first\."\)'
replacement = r'\1\n                            else:\n                                st.info("No topology loaded. Generate a topology first.")'

fixed_content = re.sub(pattern, replacement, content)

# Write the fixed content back to the file
with open('CML-NetworkBuilder/Frontend.py', 'w') as f:
    f.write(fixed_content)

print("File has been fixed.") 