import re

def clean_html():
    with open('frontend/index.html', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Remove Social Proof Booking Ticker
    content = re.sub(r'<!-- Feature HH: Social Proof Booking Ticker -->.*?<section id="process"', '<section id="process"', content, flags=re.DOTALL)
    
    # 2. Remove Eco-Impact / Sustainability
    content = re.sub(r'<!-- ============ ECO-IMPACT / SUSTAINABILITY ============ -->.*?<section id="features"', '<section id="features"', content, flags=re.DOTALL)
    
    # 3. Remove from Trust / Achievements to before Testimonials
    content = re.sub(r'<!-- ============ TRUST / ACHIEVEMENTS ============ -->.*?<!-- ============ TESTIMONIALS ============ -->', '<!-- ============ TESTIMONIALS ============ -->', content, flags=re.DOTALL)
    
    # 4. Remove from the broken Mobile App CTA (now marked as <section id="network") to the REAL network section
    # Let's find the first occurrence of <section id="network" which has phone-mockup inside it.
    # And replace everything from it to the next <section id="network"
    content = re.sub(r'<section id="network" class="py-5 bg-dark text-white position-relative overflow-hidden">\s*<div class="container">\s*<div class="row align-items-center g-5">\s*<div class="col-lg-5 text-center" data-aos="fade-right">\s*<div class="phone-mockup">.*?<section id="network"', '<section id="network"', content, flags=re.DOTALL)
    
    # Fix the overlap issue by changing fixed-top to sticky-top
    content = content.replace('navbar-expand-lg fixed-top', 'navbar-expand-lg sticky-top')
    
    # Fix padding of hero section since navbar is now in flow
    content = content.replace('padding: 160px 0 100px;', 'padding: 80px 0 100px;')

    # Fix z-index issue if sticky-top is underneath announcement-bar
    # announcement-bar has z-index: 10001
    # We should make sticky-top have z-index: 10000 or 10002
    content = content.replace('id="navbarMain">', 'id="navbarMain" style="z-index: 10000;">')

    with open('frontend/index.html', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Done pruning")

if __name__ == '__main__':
    clean_html()
