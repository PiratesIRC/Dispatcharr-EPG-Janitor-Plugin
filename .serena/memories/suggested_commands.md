# Suggested Commands for Windows

## File System Navigation
```cmd
# List directory contents
dir

# Change directory
cd <directory>

# Show current directory
cd

# Create directory
mkdir <directory_name>

# Remove directory
rmdir <directory_name>

# Remove file
del <file_name>
```

## File Operations
```cmd
# View file contents
type <file_name>

# Copy file
copy <source> <destination>

# Move file
move <source> <destination>

# Search for text in files
findstr "search_term" <file_pattern>
```

## Python Commands
```cmd
# Run Python script
python <script_name>.py

# Check Python version
python --version

# Run plugin (from Dispatcharr context)
# The plugin is executed through Dispatcharr's plugin system
```

## Git Commands
```cmd
# Check status
git status

# Stage changes
git add <file>
git add .

# Commit changes
git commit -m "commit message"

# Push changes
git push

# Pull changes
git pull

# View log
git log

# View diff
git diff
```

## Project-Specific Notes
- Python version: 3.13.8
- No build or compilation steps required
- No testing framework configured
- No linting or formatting tools configured
- Plugin runs within Dispatcharr environment