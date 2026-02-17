import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	server: {
		proxy: {
			'/settings': 'http://127.0.0.1:8770',
			'/control': 'http://127.0.0.1:8770',
			'/status': 'http://127.0.0.1:8770'
		}
	}
});
