const fs = require("fs");
const path = require("path");

const target = path.join(__dirname, "..", "build", "index.html");

const html = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>st_dragdrop component</title>
    <style>
      html, body { margin: 0; padding: 0; }
      body { font-family: Arial, Helvetica, sans-serif; overflow-x: auto; }
      #root { min-height: 100%; }
    </style>
  </head>
  <body>
    <div id="root"></div>
    <script src="./static/js/bundle.js"></script>
  </body>
</html>
`;

fs.mkdirSync(path.dirname(target), { recursive: true });
fs.writeFileSync(target, html, "utf8");
console.log("Wrote", target);
