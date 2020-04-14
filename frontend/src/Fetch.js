import store from "./Store";

const Fetch = (...props) => {
  const url = props[0];

  // Assume the API endpoint is not "private".
  // A private API endpoint is one whose word starts with an underscore.
  // These are endpoints that don't make sense to use outside the frontend app.
  let privateEndpoint = false;
  if (url.indexOf("/api/") > -1) {
    const endpoint = url.split("/")[2];
    if (endpoint.charAt(0) === "_") {
      privateEndpoint = true;
    }
  }
  const method = props.length > 1 && props[1].method ? props[1].method : "GET";
  let requiresAuth = false;
  if (props.length > 1) {
    if (props[1].credentials) {
      requiresAuth = true;
    }
  }
  const alreadyThere = !!store.apiRequests.find((r) => {
    return r.url === url && r.method === method;
  });
  if (!privateEndpoint && !alreadyThere) {
    store.apiRequests.unshift({ url, method, requiresAuth });
  }

  return fetch(...props);
};

export default Fetch;
