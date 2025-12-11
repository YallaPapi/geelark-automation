text = 'Rhonda Patrick (@foundmyfitness) tackles the mental battle'
special_chars = ['(', ')', '@', '#', '&', ';', '<', '>', '|', '$', '`', '\\', '"', "'"]
escaped = text
for char in special_chars + [' ']:
    if char == ' ':
        escaped = escaped.replace(char, '%s')
    else:
        escaped = escaped.replace(char, '\\' + char)
print(f'Original: {text}')
print(f'Escaped: {escaped}')
print(f'Command: input text "{escaped}"')
