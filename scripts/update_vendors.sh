#!/bin/bash
mkdir -p static/css static/js

echo "Updating Select2 CSS..."
curl -L https://cdnjs.cloudflare.com/ajax/libs/select2/4.1.0-beta.1/css/select2.min.css -o src/static/styles/select2.min.css

echo "Updating jQuery..."
curl -L https://code.jquery.com/jquery-3.6.0.min.js -o src/static/scripts/jquery-3.6.0.min.js

echo "Updating Select2 JS..."
curl -L https://cdnjs.cloudflare.com/ajax/libs/select2/4.1.0-beta.1/js/select2.min.js -o src/static/scripts/select2.min.js

echo "All vendor files updated."
