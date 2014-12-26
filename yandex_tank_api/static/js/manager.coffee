app = angular.module("ng-tank-manager", ['ui.ace'])

app.controller "TankManager", ($scope, $element, $interval) ->
  updateStatus = () ->
    $http.get("status").success (data) ->
      $scope.status = data

  $interval(updateStatus, 1000)
