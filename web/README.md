# Landing page

This is the static source for `engineeringmemory.dev`. The publishable files are
in `out/`; `.openai/hosting.json` points the hosted preview at that directory.
There is no JavaScript dependency or front-end build step. Icons are inline SVG
so they render consistently without an icon font or a third-party asset server.

To preview locally from this directory:

```bash
python3 -m http.server 8765 --directory out
```

The examples on the page are fictional and illustrate the shape of a local
context packet. Product behavior and setup instructions live in the root
`README.md` and `docs/`.

## Portainer deployment

The `site-image.yml` GitHub workflow builds `web/Dockerfile` and publishes the
static image to `ghcr.io/vladmuresan03/engineering-memory-site:main` when site
files change. The image uses unprivileged NGINX on port 8175. The container
package must be public for a Portainer host to pull it anonymously.

In Portainer, create a Git-backed stack from this repository with
`web/compose.yaml` as the Compose path. The stack joins the existing
`nginx-proxy-manager_default` network; set `PROXY_NETWORK` if your proxy uses a
different network. The Compose file publishes no host port. In Nginx Proxy
Manager, route `engineeringmemory.dev` to `http://engineering-memory-site:8175`
and configure its HTTPS certificate there. Redeploy the stack with image
re-pull after a new image is published.
