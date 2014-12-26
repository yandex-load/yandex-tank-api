app = angular.module("ng-tank-manager", ['ui.ace'])

app.controller "TankManager", ($scope, $interval, $http) ->
  updateStatus = () ->
    $http.get("status").success (data) ->
      $scope.status = data

  $interval(updateStatus, 1000)
