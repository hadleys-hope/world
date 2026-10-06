/** Resolve the exact vendored browser dependency for Node geometry checks, without npm install. */
export async function resolve(specifier, context, nextResolve) {
  if (specifier === "three")
    return {
      url: new URL("../vendor/three/build/three.module.js", import.meta.url)
        .href,
      shortCircuit: true,
    };
  return nextResolve(specifier, context);
}
