import store from './Store'

const Fetch = (...props) => {
  const url = props[0]
  const method = props.length && props[1].method ? props[1].method : 'GET'
  const alreadyThere = !!store.apiRequests.find(r => {
    return r.url === url && r.method === method
  })
  if (!alreadyThere) {
    store.apiRequests.unshift({ url, method })
  }

  return fetch(...props)
}

export default Fetch
