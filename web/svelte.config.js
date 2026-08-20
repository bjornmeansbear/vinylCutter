import adapter from '@sveltejs/adapter-node';

/** @type {import('@sveltejs/kit').Config} */
export default {
  kit: {
    // adapter-node, not a serverless adapter: this runs on the Pi next to the
    // cutter and needs a long-lived process that owns the device.
    adapter: adapter({ out: 'build' })
  }
};
