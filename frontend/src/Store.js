import { extendObservable } from 'mobx'

class Store {
  constructor() {
    extendObservable(this, {
      currentUser: null,
      signOutUrl: null,
      fetchError: null,
    })
  }
}

const store = (window.store = new Store())

export default store
