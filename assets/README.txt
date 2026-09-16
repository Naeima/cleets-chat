The CLEETS logo ships here as assets/cleets_logo.png (779 x 240 px, transparent PNG; the same file is in docs/assets/ for the Pages site).


The header is a banner in the style of the CLEETS Global Center website
(blue bar, logo at the left, navigation at the right, light sweep on the
right). app.py shows the logo about 84 px tall inside a white card so it
stands out on the blue (LOGO_CARD=0 in .env puts it directly on the blue;
for the Pages site set data-card="0" on the <img> in docs/index.html). If the file is
missing, the header draws the CLEETS wordmark ("CLEETS / Clean Energy and
Equitable Transportation Solutions / NSF-UKRI Global Center") in HTML;
SHOW_WORDMARK=1 shows the wordmark next to the logo as well.

For the GitHub Pages site copy the same file to docs/assets/cleets_logo.png.
