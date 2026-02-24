import adapter from '@sveltejs/adapter-static';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	kit: {
		adapter: adapter({
			pages: '../src/dictare/ui/dist',
			assets: '../src/dictare/ui/dist',
			fallback: 'index.html',
			precompress: false,
			strict: false
		}),
		paths: {
			base: '/ui'
		}
	}
};

export default config;
