/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 */
import { action, extendObservable } from "mobx";

class Store {
  constructor() {
    extendObservable(this, {
      currentUser: null,
      signInUrl: null,
      signOutUrl: null,
      fetchError: null,
      notificationMessage: null,
      setNotificationMessage: action(
        (message, success = true, warning = false) => {
          if (warning) {
            success = false;
          }
          this.notificationMessage = {
            message,
            warning,
            success,
          };
        }
      ),
      redirectTo: null,
      apiRequests: [],
      resetApiRequests: action(() => {
        this.apiRequests = [];
      }),
      setRedirectTo: action((destination, message = null) => {
        if (typeof destination === "string") {
          destination = {
            pathname: destination,
          };
        }
        this.redirectTo = destination;
        if (message) {
          if (typeof message === "string") {
            this.notificationMessage = {
              message: message,
              warning: true,
            };
          } else {
            this.notificationMessage = message;
          }
        }
      }),
      resetRedirectTo: action(() => {
        this.redirectTo = null;
      }),
      get hasPermission() {
        return (codename) => {
          if (this.currentUser) {
            if (this.currentUser.is_superuser) {
              return true;
            } else {
              // need to bother looping over permissions
              return !!this.currentUser.permissions.find((p) => {
                return p.codename === codename;
              });
            }
          }
          return false;
        };
      },
    });
  }
}

const store = (window.store = new Store());

export default store;
