import browser_cookie3

cj = browser_cookie3.edge(domain_name='douyin.com')
with open('D:/1989n/stock_analysis/douyin_cookies.txt', 'w') as f:
    f.write('# Netscape HTTP Cookie File\n')
    f.write('# https://curl.haxx.se/docs/http-cookies.html\n\n')
    for c in cj:
        # Skip session cookies (expires = None or 0 or negative)
        expires_val = c.expires
        if not expires_val or int(expires_val) <= 0:
            continue
        domain = c.domain if c.domain else 'douyin.com'
        # Netscape format: domain_specified (col2) must be TRUE only if domain has leading dot
        domain_specified = 'TRUE' if domain.startswith('.') else 'FALSE'
        # Ensure domain flag consistency: if domain has no dot at start, domain_specified must be FALSE
        # Some browsers give domain with dot prefix, some without
        path = c.path if c.path else '/'
        secure = 'TRUE' if c.secure else 'FALSE'
        expires = str(int(expires_val))
        f.write(f'{domain}\t{domain_specified}\t{path}\t{secure}\t{expires}\t{c.name}\t{c.value}\n')

count = sum(1 for _ in open('D:/1989n/stock_analysis/douyin_cookies.txt')) - 3
print(f'Saved {count} cookies from Edge to douyin_cookies.txt')
