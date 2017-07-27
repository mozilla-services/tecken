// import { extendObservable, ObservableMap } from 'mobx'
import { action, extendObservable } from 'mobx'

class Store {
  constructor() {
    extendObservable(this, {
      currentUser: null,
      signOutUrl: null,
      fetchError: null,
      apiRequests: [],
      resetApiRequests: action(() => {
        this.apiRequests = []
      }),
      get hasPermission() {
        return perm => {
          return (
            this.currentUser &&
            (this.currentUser.is_superuser ||
              this.currentUser.permissions.contains(perm))
          )
        }
      }
    })
  }
}

const store = (window.store = new Store())

export default store
